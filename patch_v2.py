import os

# 1. Рефакторинг app.py
with open('/opt/Azrail-Laba/app.py', 'r', encoding='utf-8') as f:
    code = f.read()

start_idx = code.find("def login_required(f):")
if start_idx != -1:
    routes = code[start_idx:]
    
    new_app = """import os, subprocess, time, json, re, psutil
from flask import Flask, render_template, request, redirect, url_for, Response, session, flash, jsonify
from datetime import datetime
from functools import wraps

from config import *
from utils import *

app = Flask(__name__)
app.secret_key = "SUPER_SECRET_SESSION_KEY_FOR_AMNEZIA_PANEL_2026"

""" + routes

    ping_api = """
# --- Сетевой мониторинг ---
@app.route('/api/network_stats')
@login_required
def network_stats():
    user_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if user_ip and ',' in user_ip: user_ip = user_ip.split(',')[0].strip()
    
    def do_ping(ip):
        try:
            out = subprocess.check_output(["ping", "-c", "3", "-W", "1", ip], universal_newlines=True)
            match = re.search(r"rtt min/avg/max/mdev = [\d\.]+/(?P<avg>[\d\.]+)", out)
            if match: return f"{float(match.group('avg')):.1f} ms"
        except: pass
        return "Недоступен"

    nodes = {"Локальный сервер": "127.0.0.1", "Шлюз VPN": f"{SERVER_SUBNET}.1"}
    return jsonify({"user_ip": user_ip, "nodes": {name: do_ping(ip) for name, ip in nodes.items()}, "final_ping": do_ping(user_ip) if user_ip else "Неизвестно"})

@app.route('/api/speedtest_download')
@login_required
def speedtest_download():
    return b"0" * (1024 * 1024 * 5), 200, {'Content-Type': 'application/octet-stream', 'Content-Disposition': 'attachment; filename=speedtest.bin'}

"""
    new_app = new_app.replace('if __name__ == "__main__":', ping_api + 'if __name__ == "__main__":')
    # Учитываем ваш кастомный порт (теперь он будет динамически читаться из окружения, либо останется 80)
    new_app = new_app.replace('port=80', 'port=int(os.environ.get("PANEL_PORT", 80))')

    with open('/opt/Azrail-Laba/app.py', 'w', encoding='utf-8') as f:
        f.write(new_app)

# 2. Интеграция виджета в cabinet.html
cab_path = '/opt/Azrail-Laba/templates/cabinet.html'
if os.path.exists(cab_path):
    with open(cab_path, 'r', encoding='utf-8') as f:
        html = f.read()
    
    widget = """
<div class="card" style="margin-top: 20px; padding: 15px; border: 1px solid #ddd; border-radius: 5px;">
    <h3>Сетевой статус</h3>
    <p>Ваш IP: <strong id="user-ip">Определяется...</strong></p>
    <table style="width: 100%; border-collapse: collapse; text-align: left;">
        <tr style="border-bottom: 2px solid #eee;"><th>Узел</th><th>Ping</th><th>Скорость</th></tr>
        <tbody id="network-nodes-body"></tbody>
        <tr style="border-top: 2px solid #eee; font-weight: bold;">
            <td>Вы ↔ Панель</td><td id="final-ping">Замер...</td><td id="final-speed">Замер...</td>
        </tr>
    </table>
</div>
<script>
document.addEventListener("DOMContentLoaded", function() {
    fetch('/api/network_stats').then(r=>r.json()).then(d=>{
        document.getElementById('user-ip').innerText = d.user_ip;
        document.getElementById('final-ping').innerText = d.final_ping;
        let tb = document.getElementById('network-nodes-body');
        for (const [name, ping] of Object.entries(d.nodes)) {
            tb.innerHTML += `<tr><td>${name}</td><td>${ping}</td><td><span style="color:gray;">Серверный</span></td></tr>`;
        }
    });
    let st = Date.now();
    fetch('/api/speedtest_download').then(r=>r.blob()).then(b=>{
        let dur = (Date.now() - st)/1000;
        document.getElementById('final-speed').innerText = (((b.size/(1024*1024))*8)/dur).toFixed(2) + " Mbps";
    }).catch(() => document.getElementById('final-speed').innerText = "Ошибка");
});
</script>
"""
    if 'Виджет сетевого мониторинга' not in html:
        if '{% endblock %}' in html:
            parts = html.rsplit('{% endblock %}', 1)
            html = parts[0] + widget + '\n{% endblock %}' + parts[1]
        else:
            html = html.replace('</body>', widget + '\n</body>') if '</body>' in html else html + widget
        with open(cab_path, 'w', encoding='utf-8') as f:
            f.write(html)
