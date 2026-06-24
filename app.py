from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS  # Добавлено для предотвращения CORS-ошибок в браузере пользователей
from kerykeion import AstrologicalSubjectFactory
import os

app = Flask(__name__)
CORS(app)  # Разрешаем кросс-доменные запросы, чтобы интерфейс без проблем общался с бэкендом

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

# Профессиональная база трактовок с акцентом на бизнес-стратегию и потенциал личностного роста
INTERPRETATIONS = {
    "Sun": "Солнце символизирует ваше ядро личности, волю, лидерский потенциал и авторскую позицию в бизнесе и жизни.",
    "Moon": "Луна отражает внутренние потребности, адаптационные механизмы, уровень стрессоустойчивости и интуитивное восприятие рисков.",
    "Mercury": "Меркурий управляет стилем коммуникации, бизнес-мышлением, скоростью обработки данных и финансовой логикой.",
    "Venus": "Венера определяет ваши ценности, отношение к материальным ресурсам, партнерский выбор и способность привлекать финансы.",
    "Mars": "Марс показывает способ действия, предпринимательскую активность, решительность и стратегию преодоления кризисных ситуаций.",
    "Jupiter": "Юпитер указывает на зоны стратегического масштабирования, новые возможности, авторитет и главные точки финансового роста.",
    "Saturn": "Сатурн отвечает за структуру, дисциплину, долгосрочное планирование, управление рисками и внутреннюю стабильность.",
    "Uranus": "Уран символизирует инновации, инсайты, готовность к изменениям, масштабные реформы и форс-мажорные финансовые стратегии.",
    "Neptune": "Нептун связан с интуицией, масштабным видением трендов, психологическим капиталом и скрытыми возможностями рынка.",
    "Pluto": "Плутон представляет управление крупными объемами энергии и капитала, трансформации, бизнес-власть и инвестиционные риски.",
    "Chiron": "Хирон указывает на способность находить нестандартные дипломатические решения и совмещать противоположности в делах.",
    "Lilith": "Лилит (Черная Луна) показывает зоны возможных финансовых иллюзий, скрытых психологических триггеров и точек соблазна.",
    "Mean_Node": "Северный Узел указывает на вектор вашего стратегического развития, эволюционную задачу и новые горизонты в карьере."
}

@app.route('/api/calculate', methods=['POST', 'OPTIONS'])  # Добавлен метод OPTIONS для корректной работы CORS-запросов
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
        
        # Передаем часовой пояс.
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

        # Собираем данные планет вместе с трактовками
        planets_data = []
        for p in subject.planets_list:
            if p.name in PLANET_NAMES_RU: # Берем только основные
                planets_data.append({
                    "id": p.name,
                    "name": PLANET_NAMES_RU[p.name],
                    "symbol": PLANET_SYMBOLS.get(p.name, "?"),
                    "longitude": float(p.position),
                    "interpretation": INTERPRETATIONS.get(p.name, "Описание для этой точки находится в процессе добавления.")  # Трактовка уходит на фронтенд
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
        print(f"Ошибка при расчете натальной карты: {e}")  # Появится в логах хостинга при сбое
        return jsonify({"status": "error", "message": str(e)}), 400

# Главная страница (добавлена поддержка HEAD для проверки доступности сервера хостингом)
@app.route('/', methods=['GET', 'HEAD'])
def index():
    if request.method == 'HEAD':
        return '', 200
        
    try:
        # Читаем ваш HTML-файл, который лежит в той же папке
        with open('index.html', 'r', encoding='utf-8') as f:
            html_content = f.read()
        return render_template_string(html_content)
    except FileNotFoundError:
        return "Критическая ошибка: Файл index.html не найден в корневой директории проекта.", 404

if __name__ == '__main__':
    app.run()