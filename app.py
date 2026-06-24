from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from kerykeion import AstrologicalSubjectFactory
import os

app = Flask(__name__)
CORS(app)

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

# Профессиональная база бизнес-трактовок
INTERPRETATIONS = {
    "Sun": "Солнце символизирует ваше ядро личности, волю, лидерский потенциал и авторскую позицию в бизнесе и жизни.",
    "Moon": "Луна отражает внутренние потребности, адаптационные механизмы, уровень стрессоустойчивости и интуитивное восприятие рисков.",
    "Mercury": "Меркурий управляет стилем коммуникации, бизнес-мышлением, скоростью обработки данных и финансовой логикой.",
    "Venus": "Венера определяет ваши ценности, отношение к материальным ресурсам, партнерский выбор и способность привлекать финансы.",
    "Mars": "Марс показывает способ действия, предпринимательскую активность, решительность и стратегию преодоления кризисных ситуаций.",
    "Jupiter": "Юпитер указывает на зоны стратегического масштабирования, новые возможности, авторитет и главные точки финансового роста.",
    "Saturn": "Сатурн отвечает за структуру, дисциплину, долгосрочное планирование, управление рисками и внутреннюю стабильность.",
    "Uranus": "Уран символизирует инновации, инсайты, готовность к изменениям, масштабные реформы и форс-мажорные стратегии.",
    "Neptune": "Нептун связан с интуицией, масштабным видением трендов, психологическим капиталом и скрытыми возможностями рынка.",
    "Pluto": "Плутон представляет управление крупными объемами энергии и капитала, трансформации, бизнес-власть и инвестиционные риски.",
    "Chiron": "Хирон указывает на способность находить нестандартные дипломатические решения и совмещать противоположности в делах.",
    "Lilith": "Лилит (Черная Луна) показывает зоны возможных финансовых иллюзий, скрытых психологических триггеров и точек соблазна.",
    "Mean_Node": "Северный Узел указывает на вектор вашего стратегического развития, эволюционную задачу и новые горизонты в карьере."
}

@app.route('/api/calculate', methods=['POST', 'OPTIONS'])
def calculate():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
        
    data = request.json
    try:
        # Парсим дату и время
        year, month, day = map(int, data['date'].split('-'))
        hour, minute = map(int, data['time'].split(':'))
        
        lat = float(data['lat'])
        lon = float(data['lon'])
        
        # Передаем часовой пояс
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

        # Собираем данные планет по обновленной структуре Kerykeion
        planets_data = []
        PLANET_MAPPING = {
            "sun": "Sun", "moon": "Moon", "mercury": "Mercury", "venus": "Venus", 
            "mars": "Mars", "jupiter": "Jupiter", "saturn": "Saturn", "uranus": "Uranus", 
            "neptune": "Neptune", "pluto": "Pluto", "chiron": "Chiron", "lilith": "Lilith", 
            "mean_node": "Mean_Node"
        }
        
        for attr_name, obj_name in PLANET_MAPPING.items():
            if hasattr(subject, attr_name):
                p = getattr(subject, attr_name)
                planets_data.append({
                    "id": obj_name,
                    "name": PLANET_NAMES_RU.get(obj_name, obj_name),
                    "symbol": PLANET_SYMBOLS.get(obj_name, "?"),
                    "longitude": float(p.abs_pos),
                    "interpretation": INTERPRETATIONS.get(obj_name, "Описание в процессе добавления.")
                })

        # Собираем данные домов по обновленной структуре Kerykeion
        houses_data = []
        HOUSE_MAPPING = [
            "first_house", "second_house", "third_house", "fourth_house", 
            "fifth_house", "sixth_house", "seventh_house", "eighth_house", 
            "ninth_house", "tenth_house", "eleventh_house", "twelfth_house"
        ]
        
        for i, attr_name in enumerate(HOUSE_MAPPING, start=1):
            if hasattr(subject, attr_name):
                h = getattr(subject, attr_name)
                houses_data.append({
                    "num": i,
                    "name": f"{i} Дом",
                    "longitude": float(h.abs_pos)
                })

        return jsonify({
            "status": "success",
            "planets": planets_data,
            "houses": houses_data
        })

    except Exception as e:
        print(f"Ошибка при расчете: {e}") 
        return jsonify({"status": "error", "message": str(e)}), 400

# Главная страница 
@app.route('/', methods=['GET', 'HEAD'])
def index():
    if request.method == 'HEAD':
        return '', 200
        
    try:
        if os.path.exists('index.html'):
            return send_file('index.html')
        elif os.path.exists('gemini-code-1782289667790.html'):
            return send_file('gemini-code-1782289667790.html')
        else:
            return "Критическая ошибка: HTML-файл интерфейса не найден.", 404
            
    except Exception as e:
        print(f"Критическая ошибка при загрузке: {e}")
        return f"Ошибка сервера: {e}", 500

if __name__ == '__main__':
    app.run()