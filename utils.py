import os, re, io, base64, time, json, hashlib, qrcode, psutil, subprocess
from config import *

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def load_users():
    if not os.path.exists(USERS_FILE): return {}
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except: return {}

def save_users(users):
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, indent=2, ensure_ascii=False)

def create_admin_if_not_exists():
    users = load_users()
    admin_exists = any(u.get('username') == 'Azrail' for u in users.values())
    if not admin_exists:
        users[str(int(time.time()))] = {
            "username": "Azrail", "phone": "+79994426528", "password_hash": hash_password("220823"),
            "role": "admin", "created_at": time.time(), "login_attempts": 0, "blocked_until": 0,
            "is_active": True, "is_protected": True
        }
        save_users(users)
create_admin_if_not_exists()

def clean_phone(phone_str):
    digits = re.sub(r'\D', '', phone_str)
    if not digits: return ""
    if digits.startswith('8') and len(digits) == 11: return "+7" + digits[1:]
    if digits.startswith('7') and len(digits) == 11: return "+" + digits
    if len(digits) == 10: return "+7" + digits
    return "+" + digits

def run_docker_cmd(cmd):
    res = subprocess.run(f"sudo docker exec {CONTAINER} {cmd}", shell=True, capture_output=True, text=True)
    return res.returncode, res.stdout, res.stderr

def write_docker_file(path, content):
    p = subprocess.Popen(f"sudo docker exec -i {CONTAINER} sh -c 'cat > {path}'", shell=True, stdin=subprocess.PIPE, text=True)
    p.communicate(input=content)

def append_docker_file(path, content):
    p = subprocess.Popen(f"sudo docker exec -i {CONTAINER} sh -c 'cat >> {path}'", shell=True, stdin=subprocess.PIPE, text=True)
    p.communicate(input=content)

def generate_wg_keys_via_docker():
    _, priv_key, _ = run_docker_cmd("wg genkey")
    priv_key = priv_key.strip()
    p = subprocess.Popen(f"sudo docker exec -i {CONTAINER} wg pubkey", shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    pub_key, _ = p.communicate(input=priv_key)
    return priv_key, pub_key.strip()

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
    interface_lines = [
        "[Interface]", f"Address = {ip}/32", "DNS = 1.1.1.1, 1.0.0.1", f"PrivateKey = {privkey_display}",
        f"Jc = {AMNEZIA_PARAMS['Jc']}", f"Jmin = {AMNEZIA_PARAMS['Jmin']}", f"Jmax = {AMNEZIA_PARAMS['Jmax']}",
        f"S1 = {AMNEZIA_PARAMS['S1']}", f"S2 = {AMNEZIA_PARAMS['S2']}", f"S3 = {AMNEZIA_PARAMS['S3']}", f"S4 = {AMNEZIA_PARAMS['S4']}",
        f"H1 = {AMNEZIA_PARAMS['H1']}", f"H2 = {AMNEZIA_PARAMS['H2']}", f"H3 = {AMNEZIA_PARAMS['H3']}", f"H4 = {AMNEZIA_PARAMS['H4']}"
    ]
    for i in range(1, 6):
        if AMNEZIA_PARAMS.get(f'I{i}'): interface_lines.append(f"I{i} = {AMNEZIA_PARAMS[f'I{i}']}")
    peer_lines = [
        "", "[Peer]", f"PublicKey = {SERVER_PUBLIC_KEY}", f"PresharedKey = {client_psk if client_psk else SERVER_PSK}",
        "AllowedIPs = 0.0.0.0/0, ::/0", f"Endpoint = {SERVER_ENDPOINT}", "PersistentKeepalive = 25"
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
                wg_stats[parts[0].strip()] = {'handshake_raw': parts[4].strip(), 'handshake': format_handshake(parts[4].strip()), 'rx': format_bytes(parts[5].strip()), 'tx': format_bytes(parts[6].strip())}
    name_map, priv_key_map, user_id_map, phone_map, psk_map = {}, {}, {}, {}, {}
    if os.path.exists(LOCAL_DB_PATH):
        with open(LOCAL_DB_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                if "=" in line:
                    ip, data = line.strip().split("=", 1)
                    parts = data.split("|")
                    name_map[ip] = parts[0] if len(parts) > 0 else "Client"
                    priv_key_map[ip] = parts[1] if len(parts) > 1 else ""
                    user_id_map[ip] = parts[2] if len(parts) > 2 else ""
                    phone_map[ip] = parts[3] if len(parts) > 3 else ""
                    psk_map[ip] = parts[4] if len(parts) > 4 else ""
    clients = []
    if content:
        for idx, peer_block in enumerate(content.split("[Peer]")[1:], start=1):
            pi = {k.strip(): v.strip() for line in peer_block.strip().splitlines() if "=" in line for k, v in [line.split("=", 1)]}
            pubkey = pi.get('PublicKey', '')
            ip_clean = pi.get('AllowedIPs', '').split("/")[0] if pi.get('AllowedIPs') else ""
            stats = wg_stats.get(pubkey, {'handshake': 'никогда', 'rx': '0 Б', 'tx': '0 Б', 'handshake_raw': '0'})
            is_active = False
            try:
                if int(stats['handshake_raw']) > 0 and (int(time.time()) - int(stats['handshake_raw'])) < 300: is_active = True
            except: pass
            client_conf = generate_client_config(ip_clean, priv_key_map.get(ip_clean, ""), psk_map.get(ip_clean, pi.get('PresharedKey', '')))
            img = qrcode.make(client_conf)
            buf = io.BytesIO()
            img.save(buf)
            clients.append({
                'name': name_map.get(ip_clean, f"Client-{idx}"), 'ip': ip_clean, 'pubkey': pubkey,
                'qr': base64.b64encode(buf.getvalue()).decode('utf-8'), 'conf': client_conf,
                'handshake': stats['handshake'], 'rx': stats['rx'], 'tx': stats['tx'],
                'active': is_active, 'user_id': user_id_map.get(ip_clean, ""), 'phone': phone_map.get(ip_clean, "")
            })
    return clients

def load_news():
    if not os.path.exists(NEWS_FILE): return {"news": []}
    try:
        with open(NEWS_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except: return {"news": []}

def save_news(data):
    with open(NEWS_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False, indent=2)
