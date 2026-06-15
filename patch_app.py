import sys

filepath = "/opt/Azrail-Laba/app.py"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# Фикс 1: Глобальный обработчик пользователя для сайдбара
patch_context = """
@app.context_processor
def inject_user():
    if 'user_id' in session:
        return dict(user=load_users().get(session['user_id']))
    return dict(user=None)

"""
if "@app.context_processor" not in content:
    content = content.replace("if __name__ == '__main__':", patch_context + "if __name__ == '__main__':")

# Фикс 2: Исправляем отображение конфигов конкретного пользователя
old_render = 'return render_template(\'index.html\', clients=clients, debug_log=f"Конфигурации пользователя: {user[\'username\']}", is_authed=True)'
new_render = "return render_template('user_clients.html', clients=clients, target_user=user, is_authed=True)"
content = content.replace(old_render, new_render)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)
print("✅ Бэкенд (app.py) успешно пропатчен!")
