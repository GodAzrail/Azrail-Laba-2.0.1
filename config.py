import os
import json
import subprocess
import urllib.request

PASSWORD = "220823"
CONTAINER = "amnezia-awg2"
CONF_PATH = "/opt/amnezia/awg/awg0.conf"

DB_DIR = "/opt/Azrail-Data"
LOCAL_DB_PATH = os.path.join(DB_DIR, "custom_clients.txt")
USERS_FILE = os.path.join(DB_DIR, "users.json")
HISTORY_FILE = os.path.join(DB_DIR, "traffic_history.json")
NEWS_FILE = os.path.join(DB_DIR, "news.json")
SETTINGS_FILE = os.path.join(DB_DIR, "settings.json")

def auto_discover_server_settings():
    """Автоматически сканирует окружение нового сервера и собирает рабочий конфиг"""
    # Базовый каркас на случай, если докер еще не запущен
    settings = {
        "SERVER_PUBLIC_KEY": "j6dPo7y80Z78p27BuxvyW3uLRIL2Pf1D81VN1pCosD4=",
        "SERVER_ENDPOINT": "127.0.0.1:49144",
        "SERVER_PSK": "oJwfFzzKL8M5l5H93II59RBKq66op5pXZ8AT6CEZy6U=",
        "SERVER_SUBNET": "10.8.1",
        "AMNEZIA_PARAMS": {
            "Jc": "4", "Jmin": "10", "Jmax": "50",
            "S1": "105", "S2": "98", "S3": "20", "S4": "4",
            "H1": "38853330-1516475013", "H2": "1589861663-1904702024",
            "H3": "2143975044-2144623283", "H4": "2145091347-2145797818",
            "I1": "", "I2": "", "I3": "", "I4": "", "I5": ""
        }
    }
    
    try:
        # 1. Заглядываем в конфиг Amnezia внутри контейнера
        res = subprocess.run(f"sudo docker exec {CONTAINER} cat {CONF_PATH}", shell=True, capture_output=True, text=True)
        if res.returncode == 0 and res.stdout:
            conf = res.stdout
            server_priv = ""
            listen_port = ""
            
            for line in conf.splitlines():
                line = line.strip()
                if not line or line.startswith('#'): continue
                if line == "[Peer]": break # Интересует только серверная часть [Interface]
                
                if "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip()
                    
                    if k == "PrivateKey": server_priv = v
                    elif k == "ListenPort": listen_port = v
                    elif k == "Address":
                        parts = v.split('/')[0].split('.')
                        if len(parts) == 4: settings["SERVER_SUBNET"] = f"{parts[0]}.{parts[1]}.{parts[2]}"
                    elif k in ["Jc", "Jmin", "Jmax", "S1", "S2", "S3", "S4", "H1", "H2", "H3", "H4", "I1", "I2", "I3", "I4", "I5"]:
                        settings["AMNEZIA_PARAMS"][k] = v
            
            # 2. Вычисляем Public Key из Private Key сервера через бинарник awg
            if server_priv:
                p = subprocess.Popen(f"sudo docker exec -i {CONTAINER} awg pubkey", shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
                pubkey, _ = p.communicate(input=server_priv)
                if pubkey.strip():
                    settings["SERVER_PUBLIC_KEY"] = pubkey.strip()
            
            # 3. Автоматически определяем внешний публичный IP текущего сервера
            try:
                public_ip = urllib.request.urlopen('https://api.ipify.org', timeout=3).read().decode('utf-8').strip()
            except:
                public_ip = "127.0.0.1"
                
            if listen_port:
                settings["SERVER_ENDPOINT"] = f"{public_ip}:{listen_port}"
                
    except Exception as e:
        print(f"[!] Ошибка автоопределения параметров: {e}")
        
    return settings

# --- ИНИЦИАЛИЗАЦИЯ НАСТРОЕК ПРИ СТАРТЕ ПАНЕЛИ ---
if os.path.exists(SETTINGS_FILE):
    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            active_settings = json.load(f)
    except:
        active_settings = auto_discover_server_settings()
else:
    # Если файла настроек нет (новый сервер), запускаем автопоиск и сохраняем на диск
    active_settings = auto_discover_server_settings()
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(active_settings, f, indent=4, ensure_ascii=False)

# Экспортируем переменные в глобальное пространство приложения
SERVER_PUBLIC_KEY = active_settings.get("SERVER_PUBLIC_KEY", "")
SERVER_ENDPOINT = active_settings.get("SERVER_ENDPOINT", "")
SERVER_PSK = active_settings.get("SERVER_PSK", "")
SERVER_SUBNET = active_settings.get("SERVER_SUBNET", "10.8.1")
AMNEZIA_PARAMS = active_settings.get("AMNEZIA_PARAMS", {})
