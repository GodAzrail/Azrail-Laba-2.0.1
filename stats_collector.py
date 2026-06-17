import subprocess
import os
import json
import time
from datetime import datetime

CONTAINER = "amnezia-awg2"
DB_DIR = "/opt/Azrail-Data"
HISTORY_FILE = os.path.join(DB_DIR, "traffic_history.json")

def run_docker_cmd(cmd):
    full_cmd = f"sudo docker exec {CONTAINER} {cmd}"
    res = subprocess.run(full_cmd, shell=True, capture_output=True, text=True)
    return res.stdout

def collect():
    wg_dump = run_docker_cmd("wg show awg0 dump")
    current_rx = 0
    current_tx = 0
    
    if wg_dump:
        for line in wg_dump.splitlines():
            parts = line.split("\t")
            if len(parts) >= 8:
                try:
                    current_rx += int(parts[5].strip())
                    current_tx += int(parts[6].strip())
                except:
                    continue

    today = datetime.now().strftime("%Y-%m-%d")
    
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r') as f:
            try: data = json.load(f)
            except: data = {}
    else:
        data = {}

    if "totals" not in data:
        data["totals"] = {"last_rx": current_rx, "last_tx": current_tx}
    if "history" not in data:
        data["history"] = {}

    last_rx = data["totals"].get("last_rx", current_rx)
    last_tx = data["totals"].get("last_tx", current_tx)

    # Если сервер перезапускался или счетчики сбросились
    if current_rx < last_rx: last_rx = 0
    if current_tx < last_tx: last_tx = 0

    diff_rx = current_rx - last_rx
    diff_tx = current_tx - last_tx

    if today not in data["history"]:
        data["history"][today] = {"rx": 0, "tx": 0}

    data["history"][today]["rx"] += diff_rx
    data["history"][today]["tx"] += diff_tx
    
    data["totals"] = {"last_rx": current_rx, "last_tx": current_tx}

    with open(HISTORY_FILE, 'w') as f:
        json.dump(data, f, indent=2)

if __name__ == "__main__":
    collect()
