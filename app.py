from flask import Flask, request, jsonify, render_template_string
from kerykeion import AstrologicalSubjectFactory
import os

app = Flask(__name__)

# Карта символов для планет
PLANET_SYMBOLS = {
    "Sun": "☉", "Moon": "☽", "Mercury": "☿", "Venus": "♀", 
    "Mars": "♂", "Jupiter": "♃", "Saturn": "♄", "Uranus": "♅", 
    "Neptune": "♆", "Pluto": "♇", "Chiron": "⚷", "Lilith": "⚸", 
    "Mean_Node": "☊"
}

# Словарь для перевода названий на русский язык
PLANET_NAMES_RU = {
    "Sun": "Солнце", "Moon": "Луна", "Mercury": "Меркурий", "Venus": "Венера",
    "Mars": "Марс", "Jupiter": "Юпитер", "Saturn": "Сатурн", "Uranus": "Уран",
    "Neptune": "Нептун", "Pluto": "Плутон", "Chiron": "Хирон", "Lilith": "Лилит",
    "Mean_Node": "Северный Узел"
}

@app.route('/api/calculate', methods=['POST'])
def calculate():
    data = request.json
    try:
        # Парсим дату и время
        year, month, day = map(int, data['date'].split('-'))
        hour, minute = map(int, data['time'].split(':'))
        
        lat = float(data['lat'])
        lon = float(data['lon'])
        
        # Передаем часовой пояс. Для простоты kerykeion поддерживает строки типа 'Europe/Moscow'.
        # Если передан числовой сдвиг (например, 3), преобразуем его в формат Etc/GMT
        # Внимание: В системе Etc/GMT знаки инвертированы (UTC+3 преобразуется в GMT-3)
        tz_offset = int(data['timezone'])
        tz_str = f"Etc/GMT{-tz_offset:+d}".replace("+", "")

        # Создаем астрологический объект через Kerykeion
        subject = AstrologicalSubjectFactory.from_birth_data(
            name=data.get('name', 'Проект'),
            year=year, month=month, day=day,
            hour=hour, minute=minute,
            lng=lon, lat=lat,
            tz_str=tz_str,
            online=False
        )

        # Собираем данные планет
        planets_data = []
        for p in subject.planets_list:
            if p.name in PLANET_NAMES_RU: # Берем только основные
                planets_data.append({
                    "id": p.name,
                    "name": PLANET_NAMES_RU[p.name],
                    "symbol": PLANET_SYMBOLS.get(p.name, "?"),
                    "longitude": float(p.position)
                })

        # Собираем данные домов (куспидов)
        houses_data = []
        for h in subject.houses_list:
            houses_data.append({
                "num": h.num,
                "name": f"{h.num} Дом",
                "longitude": float(h.position)
            })

        return jsonify({
            "status": "success",
            "planets": planets_data,
            "houses": houses_data
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

# Главная страница (отдает HTML-интерфейс)
@app.route('/')
def index():
    # Читаем ваш HTML-файл, который лежит в той же папке
    with open('index.html', 'r', encoding='utf-8') as f:
        html_content = f.read()
    return render_template_string(html_content)

if __name__ == '__main__':
    app.run()