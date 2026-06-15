import subprocess
import os
import re
import io
import base64
import time
import json
import hashlib
import qrcode
import psutil
from flask import Flask, render_template, request, redirect, url_for, Response, session, make_response, flash, jsonify
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = "SUPER_SECRET_SESSION_KEY_FOR_AMNEZIA_PANEL_2026"

PASSWORD = "220823"
CONTAINER = "amnezia-awg2"
CONF_PATH = "/opt/amnezia/awg/awg0.conf"

DB_DIR = "/opt/Azrail-Laba"
LOCAL_DB_PATH = os.path.join(DB_DIR, "custom_clients.txt")
USERS_FILE = os.path.join(DB_DIR, "users.json")
HISTORY_FILE = os.path.join(DB_DIR, "traffic_history.json")
NEWS_FILE = os.path.join(DB_DIR, "news.json")

os.makedirs(DB_DIR, exist_ok=True)

# ============ РЕАЛЬНЫЕ ПАРАМЕТРЫ СЕРВЕРА ============
SERVER_PUBLIC_KEY = "j6dPo7y80Z78p27BuxvyW3uLRIL2Pf1D81VN1pCosD4="
SERVER_ENDPOINT = "150.241.102.183:30104"
SERVER_PSK = "oJwfFzzKL8M5l5H93II59RBKq66op5pXZ8AT6CEZy6U="
SERVER_SUBNET = "10.8.1"  # Правильная подсеть сервера

# Amnezia параметры из реального конфига
AMNEZIA_PARAMS = {
    "Jc": "5",
    "Jmin": "10",
    "Jmax": "50",
    "S1": "130",
    "S2": "131",
    "S3": "48",
    "S4": "18",
    "H1": "1749849187-1777574382",
    "H2": "1862607108-2067790809",
    "H3": "2070916378-2118585698",
    "H4": "2144561861-2146132410",
    "I1": "",
    "I2": "",
    "I3": "",
    "I4": "",
    "I5": ""
}

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_users(users):
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, indent=2, ensure_ascii=False)

def create_admin_if_not_exists():
    users = load_users()
    admin_exists = any(u.get('username') == 'Azrail' for u in users.values())
    if not admin_exists:
        admin_id = str(int(time.time()))
        admin_data = {
            "username": "Azrail",
            "phone": "+79994426528",
            "password_hash": hash_password("220823"),
            "role": "admin",
            "created_at": time.time(),
            "login_attempts": 0,
            "blocked_until": 0,
            "is_active": True,
            "is_protected": True
        }
        users[admin_id] = admin_data
        save_users(users)

create_admin_if_not_exists()

def clean_phone(phone_str):
    digits = re.sub(r'\D', '', phone_str)
    if not digits:
        return ""
    if digits.startswith('8') and len(digits) == 11:
        return "+7" + digits[1:]
    if digits.startswith('7') and len(digits) == 11:
        return "+" + digits
    if len(digits) == 10:
        return "+7" + digits
    return "+" + digits

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
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
        if 'user_id' not in session:
            return redirect(url_for('login'))
        users = load_users()
        user = users.get(session['user_id'])
        if not user or user.get('role') != 'admin' or not user.get('is_active', True):
            return "Доступ запрещен", 403
        return f(*args, **kwargs)
    return decorated_function

def run_docker_cmd(cmd):
    full_cmd = f"sudo docker exec {CONTAINER} {cmd}"
    res = subprocess.run(full_cmd, shell=True, capture_output=True, text=True)
    return res.returncode, res.stdout, res.stderr

def write_docker_file(path, content):
    cmd = f"sudo docker exec -i {CONTAINER} sh -c 'cat > {path}'"
    p = subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE, text=True)
    p.communicate(input=content)

def append_docker_file(path, content):
    cmd = f"sudo docker exec -i {CONTAINER} sh -c 'cat >> {path}'"
    p = subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE, text=True)
    p.communicate(input=content)

def generate_wg_keys_via_docker():
    _, priv_key, _ = run_docker_cmd("wg genkey")
    priv_key = priv_key.strip()
    p = subprocess.Popen(f"sudo docker exec -i {CONTAINER} wg pubkey", shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    pub_key, _ = p.communicate(input=priv_key)
    pub_key = pub_key.strip()
    return priv_key, pub_key

def format_bytes(b_str):
    try: b = int(b_str)
    except: return "0 Б"
    if b < 1024: return f"{b} Б"
    elif b < 1024**2: return f"{b/1024:.1f} КБ"
    elif b < 1024**3: return f"{b/1024**2:.1f} МБ"
    else: return f"{b/1024**3:.2f} ГБ"

def format_handshake(t_str):
    try: t = int(t_str)
    except: return "никогда"
    if t == 0: return "никогда"
    diff = int(time.time()) - t
    if diff < 60: return f"{diff} сек назад"
    elif diff < 3600: return f"{diff//60} мин назад"
    else: return f"{diff//3600} ч назад"

def generate_client_config(ip, privkey_display, client_psk):
    """Генерирует РАБОЧИЙ конфиг клиента"""
    # Формируем Interface блок
    interface_lines = [
        "[Interface]",
        f"Address = {ip}/32",
        "DNS = 1.1.1.1, 1.0.0.1",
        f"PrivateKey = {privkey_display}",
        f"Jc = {AMNEZIA_PARAMS['Jc']}",
        f"Jmin = {AMNEZIA_PARAMS['Jmin']}",
        f"Jmax = {AMNEZIA_PARAMS['Jmax']}",
        f"S1 = {AMNEZIA_PARAMS['S1']}",
        f"S2 = {AMNEZIA_PARAMS['S2']}",
        f"S3 = {AMNEZIA_PARAMS['S3']}",
        f"S4 = {AMNEZIA_PARAMS['S4']}",
        f"H1 = {AMNEZIA_PARAMS['H1']}",
        f"H2 = {AMNEZIA_PARAMS['H2']}",
        f"H3 = {AMNEZIA_PARAMS['H3']}",
        f"H4 = {AMNEZIA_PARAMS['H4']}",
    ]
    
    # Добавляем I параметры только если они не пустые
    if AMNEZIA_PARAMS.get('I1'):
        interface_lines.append(f"I1 = {AMNEZIA_PARAMS['I1']}")
    if AMNEZIA_PARAMS.get('I2'):
        interface_lines.append(f"I2 = {AMNEZIA_PARAMS['I2']}")
    if AMNEZIA_PARAMS.get('I3'):
        interface_lines.append(f"I3 = {AMNEZIA_PARAMS['I3']}")
    if AMNEZIA_PARAMS.get('I4'):
        interface_lines.append(f"I4 = {AMNEZIA_PARAMS['I4']}")
    if AMNEZIA_PARAMS.get('I5'):
        interface_lines.append(f"I5 = {AMNEZIA_PARAMS['I5']}")
    
    interface_lines.append("")  # Пустая строка для разделения
    
    # Формируем Peer блок
    peer_lines = [
        "[Peer]",
        f"PublicKey = {SERVER_PUBLIC_KEY}",
        f"PresharedKey = {client_psk if client_psk else SERVER_PSK}",
        "AllowedIPs = 0.0.0.0/0, ::/0",
        f"Endpoint = {SERVER_ENDPOINT}",
        "PersistentKeepalive = 25"
    ]
    
    return "\n".join(interface_lines + peer_lines)

def get_amnezia_data():
    _, content, _ = run_docker_cmd(f"cat {CONF_PATH}")
    _, wg_dump, _ = run_docker_cmd("wg show awg0 dump")
    
    wg_stats = {}
    if wg_dump:
        for line in wg_dump.splitlines():
            parts = line.split("\t")
            if len(parts) >= 8:
                pub = parts[0].strip()
                wg_stats[pub] = {
                    'handshake_raw': parts[4].strip(),
                    'handshake': format_handshake(parts[4].strip()),
                    'rx': format_bytes(parts[5].strip()),
                    'tx': format_bytes(parts[6].strip())
                }
                
    name_map, priv_key_map, user_id_map, phone_map, psk_map = {}, {}, {}, {}, {}
    
    if os.path.exists(LOCAL_DB_PATH):
        with open(LOCAL_DB_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if "=" in line:
                    ip, data = line.split("=", 1)
                    parts = data.split("|")
                    name_map[ip] = parts[0] if len(parts) > 0 else "Client"
                    priv_key_map[ip] = parts[1] if len(parts) > 1 else ""
                    user_id_map[ip] = parts[2] if len(parts) > 2 else ""
                    phone_map[ip] = parts[3] if len(parts) > 3 else ""
                    psk_map[ip] = parts[4] if len(parts) > 4 else ""
    
    clients = []
    if content:
        peers = content.split("[Peer]")
        for idx, peer_block in enumerate(peers[1:], start=1):
            peer_info = {}
            for line in peer_block.strip().splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    peer_info[k.strip()] = v.strip()
            
            pubkey = peer_info.get('PublicKey', '').strip()
            allowed_ips = peer_info.get('AllowedIPs', '').strip()
            ip_clean = allowed_ips.split("/")[0] if allowed_ips else ""
            peer_psk = peer_info.get('PresharedKey', '').strip()
            
            client_name = name_map.get(ip_clean, f"Client-{idx}")
            privkey_display = priv_key_map.get(ip_clean, "")
            associated_user_id = user_id_map.get(ip_clean, "")
            associated_phone = phone_map.get(ip_clean, "")
            client_psk = psk_map.get(ip_clean, peer_psk)
            
            stats = wg_stats.get(pubkey, {'handshake': 'никогда', 'rx': '0 Б', 'tx': '0 Б', 'handshake_raw': '0'})
            is_active = False
            try:
                hr = int(stats['handshake_raw'])
                if hr > 0 and (int(time.time()) - hr) < 300:
                    is_active = True
            except: pass
            
            # Генерируем РАБОЧИЙ конфиг
            client_conf = generate_client_config(ip_clean, privkey_display, client_psk)
            
            img = qrcode.make(client_conf)
            buf = io.BytesIO()
            img.save(buf)
            qr_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
            
            clients.append({
                'name': client_name,
                'ip': ip_clean,
                'pubkey': pubkey,
                'qr': qr_b64,
                'conf': client_conf,
                'handshake': stats['handshake'],
                'rx': stats['rx'],
                'tx': stats['tx'],
                'active': is_active,
                'user_id': associated_user_id,
                'phone': associated_phone
            })
    return clients

@app.route('/', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('cabinet'))
        
    if request.method == 'POST':
        login_input = request.form.get('login_input', '').strip()
        password = request.form.get('password', '')
        
        users = load_users()
        target_uid = None
        target_user = None
        cleaned_input = clean_phone(login_input)
        
        for uid, u in users.items():
            if u.get('username') == login_input or u.get('phone') == cleaned_input:
                target_uid = uid
                target_user = u
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
            if target_user['login_attempts'] >= 5:
                target_user['blocked_until'] = current_time + 900
                flash("Слишком много неудачных попыток. Вход заблокирован на 15 минут.")
            else:
                flash(f"Неверный пароль. Осталось попыток: {5 - target_user['login_attempts']}")
                
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
            
        if len(password) < 6:
            flash("Пароль должен быть не менее 6 символов.")
            return render_template('register.html')
            
        if password != confirm_password:
            flash("Пароль не совпадают.")
            return render_template('register.html')
            
        users = load_users()
        for u in users.values():
            if u.get('username').lower() == username.lower():
                flash("Пользователь с таким логином уже существует.")
                return render_template('register.html')
            if u.get('phone') == cleaned_phone:
                flash("Пользователь с таким номером телефона уже существует.")
                return render_template('register.html')
                
        user_id = str(int(time.time())) + str(os.urandom(2).hex())
        users[user_id] = {
            "username": username,
            "phone": cleaned_phone,
            "password_hash": hash_password(password),
            "role": "user",
            "created_at": time.time(),
            "login_attempts": 0,
            "blocked_until": 0,
            "is_active": True,
            "is_protected": False
        }
        save_users(users)
        
        session['user_id'] = user_id
        session['username'] = username
        session['role'] = "user"
        return redirect(url_for('cabinet'))
        
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/inspect', methods=['GET', 'POST'])
def inspect():
    is_authed = 'user_id' in session
    return render_template('index.html', clients=get_amnezia_data(), debug_log="", is_authed=is_authed)

@app.route('/cabinet')
@login_required
def cabinet():
    users = load_users()
    current_user = users.get(session['user_id'])
    all_clients = get_amnezia_data()
    username_map = {uid: u['username'] for uid, u in users.items()}
    
    if current_user['role'] == 'admin':
        display_clients = all_clients
    else:
        display_clients = [c for c in all_clients if c['user_id'] == session['user_id']]
        
    return render_template('cabinet.html', user=current_user, clients=display_clients, all_users=users, username_map=username_map)

@app.route('/cabinet/create', methods=['POST'])
@login_required
def create_client():
    users = load_users()
    current_user = users.get(session['user_id'])
    
    name = request.form.get('name', '').strip()
    if not name: 
        flash("Имя клиента не может быть пустым")
        return redirect(url_for('cabinet'))
    
    target_user_id = session['user_id']
    if current_user['role'] == 'admin' and request.form.get('target_user_id'):
        target_user_id = request.form.get('target_user_id')
        
    target_user = users.get(target_user_id, current_user)
    privkey, pubkey = generate_wg_keys_via_docker()
    
    # Генерируем уникальный PSK для клиента
    _, psk, _ = run_docker_cmd("awg genpsk")
    psk = psk.strip()
    
    clients = get_amnezia_data()
    used_ips = [c['ip'] for c in clients]
    
    # Используем правильную подсеть 10.8.1.x
    next_ip = ""
    for i in range(3, 254):
        candidate = f"{SERVER_SUBNET}.{i}"
        if candidate not in used_ips:
            next_ip = candidate
            break
            
    if not next_ip:
        flash("Нет свободных IP адресов")
        return redirect(url_for('cabinet'))
    
    if next_ip and pubkey and privkey:
        # Временно сохраняем PSK
        write_docker_file("/tmp/client_psk.key", psk)
        
        new_peer = f"\n[Peer]\nPublicKey = {pubkey}\nPresharedKey = {psk}\nAllowedIPs = {next_ip}/32\n"
        append_docker_file(CONF_PATH, new_peer)
        
        # Сохраняем данные клиента вместе с PSK
        with open(LOCAL_DB_PATH, 'a', encoding='utf-8') as f:
            f.write(f"{next_ip}={name}|{privkey}|{target_user_id}|{target_user.get('phone','')}|{psk}\n")
        
        # Применяем настройки
        run_docker_cmd(f"awg set awg0 peer {pubkey} preshared-key /tmp/client_psk.key allowed-ips {next_ip}/32")
        run_docker_cmd("rm -f /tmp/client_psk.key")
        run_docker_cmd(f"ip route add {next_ip}/32 dev awg0")
        
        # Настройка маршрутизации
        run_docker_cmd("sysctl -w net.ipv4.ip_forward=1")
        _, eth_dev, _ = run_docker_cmd(r"sh -c 'ip route show | grep default | awk \"{print \$5}\"'")
        eth_dev = eth_dev.strip() if eth_dev.strip() else "eth0"
        run_docker_cmd(f"iptables -A FORWARD -i awg0 -o {eth_dev} -j ACCEPT")
        run_docker_cmd(f"iptables -t nat -A POSTROUTING -s {SERVER_SUBNET}.0/24 -j MASQUERADE")
        
        flash(f"Клиент {name} успешно создан с IP {next_ip}")
        
    return redirect(url_for('cabinet'))

@app.route('/cabinet/rename', methods=['POST'])
@login_required
def rename_client():
    ip = request.form.get('ip')
    new_name = request.form.get('name', '').strip()
    if not ip or not new_name: return redirect(url_for('cabinet'))
        
    users = load_users()
    current_user = users.get(session['user_id'])
    
    lines = []
    if os.path.exists(LOCAL_DB_PATH):
        with open(LOCAL_DB_PATH, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
    found = False
    with open(LOCAL_DB_PATH, 'w', encoding='utf-8') as f:
        for line in lines:
            if line.startswith(f"{ip}="):
                found = True
                parts = line.strip().split("=", 1)[1].split("|")
                owner_id = parts[2] if len(parts) > 2 else ""
                if current_user['role'] != 'admin' and owner_id != session['user_id']:
                    f.write(line)
                    continue
                
                privkey = parts[1] if len(parts) > 1 else ""
                uid = parts[2] if len(parts) > 2 else session['user_id']
                phone = parts[3] if len(parts) > 3 else current_user.get('phone', '')
                psk = parts[4] if len(parts) > 4 else ""
                f.write(f"{ip}={new_name}|{privkey}|{uid}|{phone}|{psk}\n")
            else:
                f.write(line)
                
    if not found:
        with open(LOCAL_DB_PATH, 'a', encoding='utf-8') as f:
            f.write(f"{ip}={new_name}||{session['user_id']}|{current_user.get('phone','')}|\n")
    return redirect(url_for('cabinet'))

@app.route('/cabinet/delete', methods=['POST'])
@login_required
def delete_client():
    pubkey = request.form.get('pubkey')
    ip = request.form.get('ip')
    if not pubkey: return redirect(url_for('cabinet'))
        
    users = load_users()
    current_user = users.get(session['user_id'])
    all_clients = get_amnezia_data()
    
    target_client = next((c for c in all_clients if c['pubkey'] == pubkey), None)
    if not target_client: return redirect(url_for('cabinet'))
    if current_user['role'] != 'admin' and target_client['user_id'] != session['user_id']:
        return "Доступ запрещен", 403
        
    _, content, _ = run_docker_cmd(f"cat {CONF_PATH}")
    blocks = content.split("[Peer]")
    new_content = blocks[0]
    for block in blocks[1:]:
        if f"PublicKey = {pubkey}" not in block and pubkey not in block:
            new_content += "[Peer]" + block
    write_docker_file(CONF_PATH, new_content.strip() + "\n")
    
    if ip and os.path.exists(LOCAL_DB_PATH):
        with open(LOCAL_DB_PATH, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        with open(LOCAL_DB_PATH, 'w', encoding='utf-8') as f:
            for line in lines:
                if not line.startswith(f"{ip}="): f.write(line)
        run_docker_cmd(f"ip route del {ip}/32 dev awg0")
        
    run_docker_cmd(f"awg set awg0 peer {pubkey} remove")
    flash(f"Клиент {target_client['name']} удален")
    return redirect(url_for('cabinet'))

@app.route('/cabinet/download/<ip>')
@login_required
def download_config(ip):
    users = load_users()
    current_user = users.get(session['user_id'])
    clients = get_amnezia_data()
    client = next((c for c in clients if c['ip'] == ip), None)
    
    if not client: return "Клиент не найден", 404
    if current_user['role'] != 'admin' and client['user_id'] != session['user_id']:
        return "Доступ запрещен", 403
        
    safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', client['name'])
    return Response(client['conf'], mimetype="application/octet-stream", headers={"Content-disposition": f"attachment; filename={safe_name}.conf"})

@app.route('/profile/change_password', methods=['POST'])
@login_required
def change_password():
    new_password = request.form.get('new_password', '')
    if len(new_password) < 6:
        flash("Новый пароль должен быть не менее 6 символов.")
        return redirect(url_for('cabinet'))
    users = load_users()
    users[session['user_id']]['password_hash'] = hash_password(new_password)
    save_users(users)
    flash("Пароль успешно обновлен.")
    return redirect(url_for('cabinet'))

@app.route('/profile/change_phone', methods=['POST'])
@login_required
def change_phone():
    new_phone = request.form.get('new_phone', '').strip()
    cleaned = clean_phone(new_phone)
    if len(cleaned) != 12 or not cleaned.startswith('+7'):
        flash("Неверный формат номера телефона.")
        return redirect(url_for('cabinet'))
    users = load_users()
    for uid, u in users.items():
        if uid != session['user_id'] and u.get('phone') == cleaned:
            flash("Этот номер телефона уже занят другим пользователем.")
            return redirect(url_for('cabinet'))
    users[session['user_id']]['phone'] = cleaned
    save_users(users)
    flash("Номер телефона успешно изменен.")
    return redirect(url_for('cabinet'))

@app.route('/admin/users')
@admin_required
def admin_users():
    users = load_users()
    clients = get_amnezia_data()
    config_counts = {}
    for c in clients:
        uid = c['user_id']
        config_counts[uid] = config_counts.get(uid, 0) + 1
        
    search = request.args.get('search', '').strip().lower()
    role_filter = request.args.get('role', '')
    status_filter = request.args.get('status', '')
    
    filtered_users = {}
    for uid, u in users.items():
        if search and (search not in u['username'].lower() and search not in u['phone']): continue
        if role_filter and u['role'] != role_filter: continue
        if status_filter:
            is_active = "active" if u['is_active'] else "blocked"
            if is_active != status_filter: continue
        filtered_users[uid] = u
    return render_template('admin_users.html', users=filtered_users, config_counts=config_counts, search=search, role_filter=role_filter, status_filter=status_filter)

@app.route('/admin/user/toggle_block', methods=['POST'])
@admin_required
def toggle_block():
    uid = request.form.get('user_id')
    users = load_users()
    if uid in users:
        if users[uid].get('is_protected'):
            flash("Нельзя заблокировать этого администратора!")
            return redirect(url_for('admin_users'))
        users[uid]['is_active'] = not users[uid]['is_active']
        save_users(users)
    return redirect(url_for('admin_users'))

@app.route('/admin/user/reset_password', methods=['POST'])
@admin_required
def reset_password():
    uid = request.form.get('user_id')
    new_pass = request.form.get('new_password', '').strip()
    if len(new_pass) < 6:
        flash("Пароль должен содержать минимум 6 символов.")
        return redirect(url_for('admin_users'))
    users = load_users()
    if uid in users:
        if users[uid].get('is_protected'):
            flash("Нельзя сбросить пароль главному администратору!")
            return redirect(url_for('admin_users'))
        users[uid]['password_hash'] = hash_password(new_pass)
        save_users(users)
        flash(f"Пароль пользователя {users[uid]['username']} успешно изменен.")
    return redirect(url_for('admin_users'))

@app.route('/admin/user/delete', methods=['POST'])
@admin_required
def delete_user():
    uid = request.form.get('user_id')
    users = load_users()
    if uid in users:
        if users[uid].get('is_protected'):
            flash("Нельзя удалить защищенного администратора!")
            return redirect(url_for('admin_users'))
        del users[uid]
        save_users(users)
        flash("Пользователь удален.")
    return redirect(url_for('admin_users'))

@app.route('/admin/user/clients/<user_id>')
@admin_required
def view_user_clients(user_id):
    users = load_users()
    user = users.get(user_id)
    if not user: return "Пользователь не найден", 404
    clients = [c for c in get_amnezia_data() if c['user_id'] == user_id]
    return render_template('user_clients.html', clients=clients, target_user=user, is_authed=True)

@app.route('/admin/stats')
@admin_required
def admin_stats():
    clients = get_amnezia_data()
    total_clients = len(clients)
    active_clients = sum(1 for c in clients if c['active'])
    
    cpu = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    sys_stats = {
        'cpu': cpu,
        'ram_total': round(ram.total / (1024**3), 1),
        'ram_used': round(ram.used / (1024**3), 1),
        'ram_percent': ram.percent,
        'disk_total': round(disk.total / (1024**3), 1),
        'disk_used': round(disk.used / (1024**3), 1),
        'disk_percent': disk.percent
    }
    
    history_data = {}
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r') as f:
                raw_history = json.load(f).get("history", {})
                for date, metrics in raw_history.items():
                    rx = metrics.get("rx", 0)
                    tx = metrics.get("tx", 0)
                    history_data[date] = {
                        'rx_formatted': format_bytes(rx), 'rx_raw': rx, 'tx_raw': tx,
                        'tx_formatted': format_bytes(tx),
                        'total_formatted': format_bytes(rx + tx)
                    }
        except:
            pass

    return render_template('stats.html', total_clients=total_clients, active_clients=active_clients, sys_stats=sys_stats, traffic_history=history_data)

def load_news():
    try:
        if not os.path.exists(NEWS_FILE):
            return {"news": []}
        with open(NEWS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading news: {e}")
        return {"news": []}

def save_news(data):
    with open(NEWS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

@app.route('/news')
def get_news():
    try:
        data = load_news()
        active_news = [n for n in data.get('news', []) if n.get('active', True)]
        return jsonify(active_news)
    except Exception as e:
        print(f"Error in /news: {e}")
        return jsonify([])

@app.route('/admin/news', methods=['GET', 'POST'])
def admin_news():
    if 'user_id' not in session:
        return redirect('/')
    
    all_users = load_users()
    user = all_users.get(session['user_id'])
    if not user or user.get('role') != 'admin':
        flash('Доступ запрещен')
        return redirect('/cabinet')
    
    if request.method == 'POST':
        action = request.form.get('action')
        data = load_news()
        
        if action == 'add':
            new_news = {
                'id': str(int(datetime.now().timestamp())),
                'title': request.form.get('title'),
                'content': request.form.get('content'),
                'date': datetime.now().strftime('%Y-%m-%d'),
                'type': request.form.get('type', 'info'),
                'active': True
            }
            data['news'].insert(0, new_news)
            save_news(data)
            flash('Новость добавлена!')
        
        elif action == 'delete':
            news_id = request.form.get('news_id')
            data['news'] = [n for n in data['news'] if n['id'] != news_id]
            save_news(data)
            flash('Новость удалена!')
        
        elif action == 'toggle':
            news_id = request.form.get('news_id')
            for n in data['news']:
                if n['id'] == news_id:
                    n['active'] = not n.get('active', True)
                    break
            save_news(data)
            flash('Статус новости изменен!')
        
        return redirect('/admin/news')
    
    data = load_news()
    return render_template('admin_news.html', news=data.get('news', []))

@app.context_processor
def inject_user():
    if 'user_id' in session:
        return dict(user=load_users().get(session['user_id']))
    return dict(user=None)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80, debug=False)