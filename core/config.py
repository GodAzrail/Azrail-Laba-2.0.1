import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'supersecretkey_change_me')
    # Укажите здесь ваш актуальный порт управления, если он отличается от стандартного
    PORT = int(os.environ.get('PANEL_PORT', 80)) 
    
    # Пути к файлам данных
    USERS_FILE = '/opt/Azrail-Laba/users.json'
    TRAFFIC_FILE = '/opt/Azrail-Laba/traffic_history.json'
    
    # Сетевые настройки
    AMNEZIA_CONTAINER = 'amnezia-awg2'
    VPN_SUBNET = '10.8.0.0/24'
