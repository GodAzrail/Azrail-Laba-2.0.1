import re

path = '/opt/Azrail-Laba/app.py'
with open(path, 'r', encoding='utf-8') as f:
    code = f.read()

# Заменяем статический IP на динамический запрос
code = re.sub(
    r'Endpoint = 150\.241\.102\.183',
    r"Endpoint = {__import__('urllib.request').request.urlopen('https://ifconfig.me').read().decode('utf-8').strip()}",
    code
)

# Заменяем статический PublicKey на динамический запрос к ядру AWG
code = re.sub(
    r'PublicKey = iljbNMHAOTnu13oei9BRPBZwF3b\+o8snYF9C1O1sD3c=',
    r"PublicKey = {run_docker_cmd('awg show awg0 public-key')[1].strip()}",
    code
)

with open(path, 'w', encoding='utf-8') as f:
    f.write(code)
print("Код успешно обновлен! Теперь панель работает автоматически.")
