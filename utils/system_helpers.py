import subprocess
import psutil
import re

def get_system_stats():
    """Получение базовой статистики сервера (CPU, RAM)."""
    return {
        "cpu": psutil.cpu_percent(interval=1),
        "ram": psutil.virtual_memory().percent
    }

def execute_ping(target_ip):
    """Пинг удаленного IP-адреса."""
    try:
        output = subprocess.check_output(["ping", "-c", "3", "-W", "1", target_ip], universal_newlines=True)
        # Ищем среднее значение пинга в выводе
        match = re.search(r"rtt min/avg/max/mdev = [\d\.]+/(?P<avg>[\d\.]+)", output)
        if match:
            return f"{float(match.group('avg')):.1f} ms"
    except Exception:
        pass
    return "Недоступен"
