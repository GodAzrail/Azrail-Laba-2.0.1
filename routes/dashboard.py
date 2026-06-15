from flask import Blueprint, render_template, request, jsonify
from utils.system_helpers import execute_ping, get_system_stats
from core.config import Config

dashboard_bp = Blueprint('dashboard', __name__)

# Список ваших независимых сетевых узлов для мониторинга (замените IP на реальные)
NETWORK_NODES = {
    "Нидерланды (Основной)": "192.168.1.10", 
    "Великобритания (Резерв)": "192.168.2.10",
    "Россия (Локальный)": "192.168.3.10"
}

@dashboard_bp.route('/api/network_stats')
def network_stats():
    # Получаем реальный IP пользователя (учитывая возможный прокси/Nginx)
    user_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if ',' in user_ip:
        user_ip = user_ip.split(',')[0].strip()

    node_pings = {}
    # 1. Тестируем пинг от сервера панели до каждого сетевого узла
    for node_name, node_ip in NETWORK_NODES.items():
        node_pings[node_name] = execute_ping(node_ip)
        
    # 2. Тестируем пинг от сервера панели напрямую до пользователя
    final_ping = execute_ping(user_ip)

    return jsonify({
        "user_ip": user_ip,
        "nodes": node_pings,
        "final_ping": final_ping
    })

@dashboard_bp.route('/api/speedtest_download')
def speedtest_download():
    """Возвращает пустой блок данных размером 5 МБ для замера скорости."""
    chunk = b"0" * (1024 * 1024 * 5) # 5 MB
    return chunk, 200, {
        'Content-Type': 'application/octet-stream',
        'Content-Disposition': 'attachment; filename=speedtest.bin'
    }
