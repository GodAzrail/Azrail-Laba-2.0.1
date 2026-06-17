import os, subprocess, time, json, re, psutil
from flask import Flask, render_template, request, redirect, url_for, Response, session, flash, jsonify
from datetime import datetime
from functools import wraps

from config import *
from utils import *

app = Flask(__name__)
app.secret_key = "SUPER_SECRET_SESSION_KEY_FOR_AMNEZIA_PANEL_2026"

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session: return redirect(url_for('login'))
        users = load_users()
        user = users.get(session['user_id'])
        if not user or not user.get('is_active', True):
            session.clear()
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session: return redirect(url_for('login'))
        users = load_users()
        user = users.get(session['user_id'])
        if not user or user.get('role') != 'admin' or not user.get('is_active', True): return "Доступ запрещен", 403
        return f(*args, **kwargs)
    return decorated_function

@app.route('/', methods=['GET', 'POST'])
def login():
    if 'user_id' in session: return redirect(url_for('cabinet'))
    if request.method == 'POST':
        login_input = request.form.get('login_input', '').strip()
        password = request.form.get('password', '')
        users = load_users()
        target_uid, target_user = None, None
        cleaned_input = clean_phone(login_input)
        for uid, u in users.items():
            if u.get('username') == login_input or u.get('phone') == cleaned_input:
                target_uid, target_user = uid, u
                break
        if not target_user:
            flash("Неверный логин/телефон или пароль.")
            return render_template('login.html')
        current_time = time.time()
        if target_user.get('blocked_until', 0) > current_time:
            rem = int(target_user['blocked_until'] - current_time)
            flash(f"Аккаунт временно заблокирован. Попробуйте через {rem // 60 + 1} мин.")
            return render_template('login.html')
        if not target_user.get('is_active', True):
            flash("Ваш аккаунт деактивирован администратором.")
            return render_template('login.html')
        if target_user['password_hash'] == hash_password(password):
            target_user['login_attempts'] = 0
            target_user['blocked_until'] = 0
            users[target_uid] = target_user
            save_users(users)
            session['user_id'] = target_uid
            session['username'] = target_user['username']
            session['role'] = target_user['role']
            return redirect(url_for('cabinet'))
        else:
            target_user['login_attempts'] = target_user.get('login_attempts', 0) + 1
            if target_user['login_attempts'] >= 5: target_user['blocked_until'] = current_time + 900
            else: flash(f"Неверный пароль. Осталось попыток: {5 - target_user['login_attempts']}")
            users[target_uid] = target_user
            save_users(users)
            return render_template('login.html')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        if not re.match(r"^[a-zA-Z0-9]{3,20}$", username):
            flash("Логин должен состоять только из латиницы и цифр (от 3 до 20 символов).")
            return render_template('register.html')
        cleaned_phone = clean_phone(phone)
        if len(cleaned_phone) != 12 or not cleaned_phone.startswith('+7'):
            flash("Номер телефона должен содержать 11 цифр.")
            return render_template('register.html')
        if len(password) < 6 or password != confirm_password:
            flash("Ошибка в паролях (минимум 6 символов, должны совпадать).")
            return render_template('register.html')
        users = load_users()
        for u in users.values():
            if u.get('username').lower() == username.lower() or u.get('phone') == cleaned_phone:
                flash("Пользователь с таким логином или телефоном уже существует.")
                return render_template('register.html')
        user_id = str(int(time.time())) + str(os.urandom(2).hex())
        users[user_id] = {"username": username, "phone": cleaned_phone, "password_hash": hash_password(password), "role": "user", "created_at": time.time(), "login_attempts": 0, "blocked_until": 0, "is_active": True, "is_protected": False}
        save_users(users)
        session['user_id'], session['username'], session['role'] = user_id, username, "user"
        return redirect(url_for('cabinet'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/inspect', methods=['GET', 'POST'])
def inspect():
    return render_template('index.html', clients=get_amnezia_data(), debug_log="", is_authed='user_id' in session)

@app.route('/cabinet')
@login_required
def cabinet():
    users = load_users()
    current_user = users.get(session['user_id'])
    all_clients = get_amnezia_data()
    username_map = {uid: u['username'] for uid, u in users.items()}
    display_clients = all_clients if current_user['role'] == 'admin' else [c for c in all_clients if c['user_id'] == session['user_id']]
    return render_template('cabinet.html', user=current_user, clients=display_clients, all_users=users, username_map=username_map)

@app.route('/cabinet/create', methods=['POST'])
@login_required
def create_client():
    users = load_users()
    current_user = users.get(session['user_id'])
    name = request.form.get('name', '').strip()
    if not name: return redirect(url_for('cabinet'))
    target_user_id = session['user_id']
    if current_user['role'] == 'admin' and request.form.get('target_user_id'): target_user_id = request.form.get('target_user_id')
    target_user = users.get(target_user_id, current_user)
    privkey, pubkey = generate_wg_keys_via_docker()
    _, psk, _ = run_docker_cmd("awg genpsk")
    psk = psk.strip()
    used_ips = [c['ip'] for c in get_amnezia_data()]
    next_ip = ""
    for i in range(3, 254):
        candidate = f"{SERVER_SUBNET}.{i}"
        if candidate not in used_ips:
            next_ip = candidate
            break
    if not next_ip: return redirect(url_for('cabinet'))
    write_docker_file("/tmp/client_psk.key", psk)
    append_docker_file(CONF_PATH, f"\n[Peer]\nPublicKey = {pubkey}\nPresharedKey = {psk}\nAllowedIPs = {next_ip}/32\n")
    with open(LOCAL_DB_PATH, 'a', encoding='utf-8') as f: f.write(f"{next_ip}={name}|{privkey}|{target_user_id}|{target_user.get('phone','')}|{psk}\n")
    run_docker_cmd(f"awg set awg0 peer {pubkey} preshared-key /tmp/client_psk.key allowed-ips {next_ip}/32")
    run_docker_cmd("rm -f /tmp/client_psk.key")
    run_docker_cmd(f"ip route add {next_ip}/32 dev awg0")
    run_docker_cmd("sysctl -w net.ipv4.ip_forward=1")
    _, eth_dev, _ = run_docker_cmd(r"sh -c 'ip route show | grep default | awk \"{print \$5}\"'")
    eth_dev = eth_dev.strip() if eth_dev.strip() else "eth0"
    run_docker_cmd(f"iptables -A FORWARD -i awg0 -o {eth_dev} -j ACCEPT")
    run_docker_cmd(f"iptables -t nat -A POSTROUTING -s {SERVER_SUBNET}.0/24 -j MASQUERADE")
    flash(f"Клиент {name} успешно создан.")
    return redirect(url_for('cabinet'))

@app.route('/cabinet/rename', methods=['POST'])
@login_required
def rename_client():
    ip, new_name = request.form.get('ip'), request.form.get('name', '').strip()
    if not ip or not new_name: return redirect(url_for('cabinet'))
    current_user = load_users().get(session['user_id'])
    lines = []
    if os.path.exists(LOCAL_DB_PATH):
        with open(LOCAL_DB_PATH, 'r', encoding='utf-8') as f: lines = f.readlines()
    with open(LOCAL_DB_PATH, 'w', encoding='utf-8') as f:
        for line in lines:
            if line.startswith(f"{ip}="):
                parts = line.strip().split("=", 1)[1].split("|")
                if current_user['role'] != 'admin' and parts[2] != session['user_id']: f.write(line)
                else: f.write(f"{ip}={new_name}|{parts[1]}|{parts[2]}|{parts[3]}|{parts[4]}\n")
            else: f.write(line)
    return redirect(url_for('cabinet'))

@app.route('/cabinet/delete', methods=['POST'])
@login_required
def delete_client():
    pubkey, ip = request.form.get('pubkey'), request.form.get('ip')
    if not pubkey: return redirect(url_for('cabinet'))
    current_user = load_users().get(session['user_id'])
    target_client = next((c for c in get_amnezia_data() if c['pubkey'] == pubkey), None)
    if not target_client or (current_user['role'] != 'admin' and target_client['user_id'] != session['user_id']): return "Доступ запрещен", 403
    _, content, _ = run_docker_cmd(f"cat {CONF_PATH}")
    blocks = content.split("[Peer]")
    new_content = blocks[0]
    for block in blocks[1:]:
        if f"PublicKey = {pubkey}" not in block and pubkey not in block: new_content += "[Peer]" + block
    write_docker_file(CONF_PATH, new_content.strip() + "\n")
    if ip and os.path.exists(LOCAL_DB_PATH):
        with open(LOCAL_DB_PATH, 'r', encoding='utf-8') as f: lines = f.readlines()
        with open(LOCAL_DB_PATH, 'w', encoding='utf-8') as f:
            for line in lines:
                if not line.startswith(f"{ip}="): f.write(line)
        run_docker_cmd(f"ip route del {ip}/32 dev awg0")
    run_docker_cmd(f"awg set awg0 peer {pubkey} remove")
    return redirect(url_for('cabinet'))

@app.route('/cabinet/download/<ip>')
@login_required
def download_config(ip):
    client = next((c for c in get_amnezia_data() if c['ip'] == ip), None)
    if not client: return "Клиент не найден", 404
    if load_users().get(session['user_id'])['role'] != 'admin' and client['user_id'] != session['user_id']: return "Доступ запрещен", 403
    return Response(client['conf'], mimetype="application/octet-stream", headers={"Content-disposition": f"attachment; filename={re.sub(r'[^a-zA-Z0-9_-]', '_', client['name'])}.conf"})

@app.route('/profile/change_password', methods=['POST'])
@login_required
def change_password():
    new_pass = request.form.get('new_password', '')
    if len(new_pass) < 6: return redirect(url_for('cabinet'))
    users = load_users()
    users[session['user_id']]['password_hash'] = hash_password(new_pass)
    save_users(users)
    return redirect(url_for('cabinet'))

@app.route('/profile/change_phone', methods=['POST'])
@login_required
def change_phone():
    cleaned = clean_phone(request.form.get('new_phone', '').strip())
    if len(cleaned) != 12 or not cleaned.startswith('+7'): return redirect(url_for('cabinet'))
    users = load_users()
    for uid, u in users.items():
        if uid != session['user_id'] and u.get('phone') == cleaned: return redirect(url_for('cabinet'))
    users[session['user_id']]['phone'] = cleaned
    save_users(users)
    return redirect(url_for('cabinet'))

@app.route('/admin/users')
@admin_required
def admin_users():
    users = load_users()
    config_counts = {}
    for c in get_amnezia_data(): config_counts[c['user_id']] = config_counts.get(c['user_id'], 0) + 1
    search, role_filter, status_filter = request.args.get('search', '').strip().lower(), request.args.get('role', ''), request.args.get('status', '')
    filtered_users = {}
    for uid, u in users.items():
        if search and (search not in u['username'].lower() and search not in u['phone']): continue
        if role_filter and u['role'] != role_filter: continue
        if status_filter and ("active" if u['is_active'] else "blocked") != status_filter: continue
        filtered_users[uid] = u
    return render_template('admin_users.html', users=filtered_users, config_counts=config_counts, search=search, role_filter=role_filter, status_filter=status_filter)

@app.route('/admin/user/toggle_block', methods=['POST'])
@admin_required
def toggle_block():
    uid = request.form.get('user_id')
    users = load_users()
    if uid in users and not users[uid].get('is_protected'):
        users[uid]['is_active'] = not users[uid]['is_active']
        save_users(users)
    return redirect(url_for('admin_users'))

@app.route('/admin/user/reset_password', methods=['POST'])
@admin_required
def reset_password():
    uid, new_pass = request.form.get('user_id'), request.form.get('new_password', '').strip()
    if len(new_pass) < 6: return redirect(url_for('admin_users'))
    users = load_users()
    if uid in users and not users[uid].get('is_protected'):
        users[uid]['password_hash'] = hash_password(new_pass)
        save_users(users)
    return redirect(url_for('admin_users'))

@app.route('/admin/user/delete', methods=['POST'])
@admin_required
def delete_user():
    uid = request.form.get('user_id')
    users = load_users()
    if uid in users and not users[uid].get('is_protected'):
        del users[uid]
        save_users(users)
    return redirect(url_for('admin_users'))

@app.route('/admin/user/clients/<user_id>')
@admin_required
def view_user_clients(user_id):
    user = load_users().get(user_id)
    if not user: return "Пользователь не найден", 404
    return render_template('user_clients.html', clients=[c for c in get_amnezia_data() if c['user_id'] == user_id], target_user=user, is_authed=True)

@app.route('/admin/stats')
@admin_required
def admin_stats():
    clients = get_amnezia_data()
    ram, disk = psutil.virtual_memory(), psutil.disk_usage('/')
    sys_stats = {'cpu': psutil.cpu_percent(interval=None), 'ram_total': round(ram.total / (1024**3), 1), 'ram_used': round(ram.used / (1024**3), 1), 'ram_percent': ram.percent, 'disk_total': round(disk.total / (1024**3), 1), 'disk_used': round(disk.used / (1024**3), 1), 'disk_percent': disk.percent}
    history_data = {}
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r') as f:
                for date, m in json.load(f).get("history", {}).items():
                    rx, tx = m.get("rx", 0), m.get("tx", 0)
                    history_data[date] = {'rx_formatted': format_bytes(rx), 'rx_raw': rx, 'tx_raw': tx, 'tx_formatted': format_bytes(tx), 'total_formatted': format_bytes(rx + tx)}
        except: pass
    return render_template('stats.html', total_clients=len(clients), active_clients=sum(1 for c in clients if c['active']), sys_stats=sys_stats, traffic_history=history_data)

@app.route('/news')
def get_news():
    return jsonify([n for n in load_news().get('news', []) if n.get('active', True)])

@app.route('/admin/news', methods=['GET', 'POST'])
def admin_news():
    if 'user_id' not in session or load_users().get(session['user_id'], {}).get('role') != 'admin': return redirect('/cabinet')
    if request.method == 'POST':
        action, data = request.form.get('action'), load_news()
        if action == 'add': data['news'].insert(0, {'id': str(int(datetime.now().timestamp())), 'title': request.form.get('title'), 'content': request.form.get('content'), 'date': datetime.now().strftime('%Y-%m-%d'), 'type': request.form.get('type', 'info'), 'active': True})
        elif action == 'delete': data['news'] = [n for n in data['news'] if n['id'] != request.form.get('news_id')]
        elif action == 'toggle':
            for n in data['news']:
                if n['id'] == request.form.get('news_id'): n['active'] = not n.get('active', True)
        save_news(data)
        return redirect('/admin/news')
    return render_template('admin_news.html', news=load_news().get('news', []))

# --- ЧЕЛОВЕЧЕСКИЙ АНАЛИЗАТОР МАРШРУТА НА БАЗЕ MTR ---
@app.route('/api/network_stats')
@login_required
def network_stats():
    user_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if user_ip and ',' in user_ip: user_ip = user_ip.split(',')[0].strip()
    try:
        import subprocess, re, os
        env = os.environ.copy()
        env["LC_ALL"] = "C"
        out = subprocess.check_output(["mtr", "--report", "--report-cycles", "2", str(user_ip)], env=env, universal_newlines=True)
        parsed_hops = []
        for line in out.splitlines():
            if not line or 'HOST' in line or 'Start:' in line: continue
            parts = line.split()
            if len(parts) < 6: continue
            raw_host = parts[1].replace('|--', '').strip()
            loss = parts[2]
            avg_ping = parts[5]
            name, desc, status = raw_host, "Промежуточный узел связи сети", "good"
            if raw_host == "_gateway":
                name = "Выход с сервера VPN"
                desc = "Стартовая точка. Трафик покидает ваш сервер в Нидерландах."
            elif "cogent" in raw_host or "atlas" in raw_host or "ams" in raw_host or "fra" in raw_host:
                name = "Европейские магистрали"
                desc = "Крупные международные каналы связи (Нидерланды / Германия). Маршрут чистый."
            elif "maxima" in raw_host or "best" in raw_host:
                name = "Ваш домашний провайдер"
                desc = "Сеть вашего интернет-провайдера, доставляющая трафик непосредственно на роутер."
            elif any(x in raw_host for x in ["188.254", "178.34", "185.82"]):
                name = "Граница сетей (Европа ↔ РФ)"
                desc = "Стык между зарубежными и российскими сетями. Самая частая зона потерь скорости."
                status = "warning"
            elif raw_host == "???":
                name = "Ваше устройство / Роутер"
                desc = "Конечный адрес. Ответ скрыт защитным файрволом устройства (это полностью безопасно)."
                avg_ping = "—"
            try:
                if avg_ping != "—" and float(avg_ping) > 85: status = "slow"
            except: pass
            parsed_hops.append({"node": name, "desc": desc, "ping": f"{float(avg_ping):.1f} ms" if avg_ping != "—" else "—", "loss": loss, "status": status})
        return jsonify({"status": "ok", "user_ip": user_ip, "hops": parsed_hops})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/speedtest_download')
@login_required
def speedtest_download():
    return b"0" * (1024 * 1024 * 5), 200, {'Content-Type': 'application/octet-stream', 'Content-Disposition': 'attachment; filename=speedtest.bin'}

@app.context_processor
def inject_user():
    if 'user_id' in session: return dict(user=load_users().get(session['user_id']))
    return dict(user=None)


@app.route('/admin/settings', methods=['GET', 'POST'])
@admin_required
def admin_settings():
    import json, subprocess
    settings_path = "/opt/Azrail-Data/settings.json"
    if request.method == 'POST':
        new_settings = {
            "SERVER_PUBLIC_KEY": request.form.get("SERVER_PUBLIC_KEY", "").strip(),
            "SERVER_ENDPOINT": request.form.get("SERVER_ENDPOINT", "").strip(),
            "SERVER_PSK": request.form.get("SERVER_PSK", "").strip(),
            "SERVER_SUBNET": request.form.get("SERVER_SUBNET", "").strip(),
            "AMNEZIA_PARAMS": {k: request.form.get(k, "").strip() for k in ["Jc", "Jmin", "Jmax", "S1", "S2", "S3", "S4", "H1", "H2", "H3", "H4", "I1", "I2", "I3", "I4", "I5"]}
        }
        with open(settings_path, 'w', encoding='utf-8') as f:
            json.dump(new_settings, f, indent=4)
        flash("Настройки сохранены! Панель автоматически перезапускается для применения новых параметров...")
        subprocess.Popen(["/opt/Azrail-Laba/restart.sh"], start_new_session=True)
        return redirect(url_for('admin_settings'))
        
    with open(settings_path, 'r', encoding='utf-8') as f:
        cur_set = json.load(f)
    return render_template('settings.html', settings=cur_set)


@app.route('/admin/settings/sync', methods=['POST'])
@admin_required
def sync_settings():
    import json, urllib.request, subprocess
    from config import SETTINGS_FILE, CONTAINER
    from utils import run_docker_cmd
    
    try:
        # Читаем конфиг сервера прямо из контейнера
        _, conf, _ = run_docker_cmd("cat /opt/amnezia/awg/awg0.conf")
        
        awg_params = {}
        server_priv = ""
        listen_port = ""
        subnet = "10.8.1"
        
        # Парсим рабочий конфиг
        for line in conf.splitlines():
            line = line.strip()
            if not line or line.startswith('#'): continue
            if line == "[Peer]": break # Нам нужен только блок [Interface]
            
            if "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip()
                
                if k == "PrivateKey": server_priv = v
                elif k == "ListenPort": listen_port = v
                elif k == "Address":
                    # Вытаскиваем подсеть (10.8.1.1/24 -> 10.8.1)
                    parts = v.split('/')[0].split('.')
                    if len(parts) == 4: subnet = f"{parts[0]}.{parts[1]}.{parts[2]}"
                elif k in ["Jc", "Jmin", "Jmax", "S1", "S2", "S3", "S4", "H1", "H2", "H3", "H4", "I1", "I2", "I3", "I4", "I5"]:
                    awg_params[k] = v

        # Генерируем публичный ключ из приватного через утилиту awg
        p = subprocess.Popen(f"sudo docker exec -i {CONTAINER} awg pubkey", shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        pubkey, _ = p.communicate(input=server_priv)
        pubkey = pubkey.strip()
        
        # Узнаем публичный IP сервера
        try:
            public_ip = urllib.request.urlopen('https://api.ipify.org', timeout=3).read().decode('utf-8').strip()
        except:
            public_ip = "127.0.0.1"

        # Открываем текущие настройки панели
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            cur_set = json.load(f)
            
        # Обновляем все значения реальными данными с сервера
        cur_set["SERVER_PUBLIC_KEY"] = pubkey
        cur_set["SERVER_ENDPOINT"] = f"{public_ip}:{listen_port}"
        cur_set["SERVER_SUBNET"] = subnet
        
        for k, v in awg_params.items():
            cur_set["AMNEZIA_PARAMS"][k] = v
            
        # Сохраняем и перезагружаемся
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(cur_set, f, indent=4)
            
        flash("Успешно! Данные вытянуты из ядра Amnezia. Панель перезапускается...")
        subprocess.Popen(["/opt/Azrail-Laba/restart.sh"], start_new_session=True)
        return redirect(url_for('admin_settings'))
    except Exception as e:
        flash(f"Ошибка синхронизации: {str(e)}")
        return redirect(url_for('admin_settings'))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80, debug=False)
