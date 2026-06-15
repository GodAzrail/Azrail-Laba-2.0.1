# 🛡️ Azrail-Laba VPN Panel v2.0

Современная панель управления сетевой инфраструктурой и VPN-клиентами на базе **AmneziaWG** с умной синхронизацией и встроенной сетевой аналитикой.

## ✨ Ключевые возможности
* 🔄 **Умная синхронизация (Plug & Play):** Автоматическое чтение конфигурации (`awg0.conf`), ключей и параметров обфускации (DPI) напрямую из Docker-контейнера при первом запуске.
* 📊 **Продвинутая статистика:** Дашборд с мониторингом нагрузки на процессор, оперативную память, жесткий диск и графиком расхода трафика.
* 🌐 **Встроенный MTR-виджет:** Интеллектуальная трассировка маршрута от сервера до клиента прямо в браузере с понятными расшифровками промежуточных узлов связи.
* 📱 **Удобный личный кабинет:** Создание профилей, генерация увеличенных QR-кодов и скачивание конфигураций в один клик.

---

## ⚙️ Требования системы
* **ОС:** Ubuntu 22.04+
* **Установленные пакеты:** Python 3.10+, `python3-venv`, `traceroute`, `mtr`
* **Права:** `root` (для работы на 80-м порту и управления маршрутизацией `iptables`)
* **Ядро VPN:** Установленный и запущенный контейнер `amnezia-awg2`

---

## 🚀 Быстрая установка на новый сервер

**1. Клонирование репозитория**
```bash
git clone [https://github.com/GodAzrail/azrail-laba-v2.0.git](https://github.com/GodAzrail/azrail-laba-v2.0.git) /opt/Azrail-Laba
cd /opt/Azrail-Laba
```

**2. Настройка системы и окружения**
```bash
sudo apt update && sudo apt install -y python3-venv traceroute mtr
sudo sysctl -w net.ipv4.ip_forward=1
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

**3. Запуск панели**
```bash
chmod +x /opt/Azrail-Laba/restart.sh
/opt/Azrail-Laba/restart.sh
```

---

## 🔄 Обновление уже запущенной панели
Если панель уже работает, и вы хотите подтянуть свои последние изменения из GitHub:

```bash
cd /opt/Azrail-Laba
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
chmod +x /opt/Azrail-Laba/restart.sh
/opt/Azrail-Laba/restart.sh
```

> **Примечание по безопасности:** Ваши конфиденциальные файлы (`settings.json`, `users.json`, `traffic_history.json`) надежно защищены файлом `.gitignore`. Они **не будут стерты или перезаписаны** при выполнении команды `git pull`.
