from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from kerykeion import AstrologicalSubjectFactory
from timezonefinder import TimezoneFinder
from zoneinfo import ZoneInfo
from datetime import datetime
import os
import pymysql
import pymysql.cursors

app = Flask(__name__)
CORS(app)

# Данные для подключения к БД лежат в config.py прямо на сервере (не в гите —
# файл с паролем от базы не должен попадать в публичный репозиторий)
try:
    from config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME
except ImportError:
    DB_HOST = DB_USER = DB_PASSWORD = DB_NAME = None

def get_db_connection():
    if not DB_HOST:
        raise RuntimeError("База данных не настроена (нет config.py на сервере)")
    return pymysql.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor, charset='utf8mb4'
    )
tf = TimezoneFinder()

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

@app.route('/api/timezone', methods=['GET'])
def get_timezone():
    """Возвращает исторически верное смещение UTC для координат+даты — используется
    фронтендом, чтобы сразу показать пользователю авто-определённый часовой пояс."""
    try:
        lat = float(request.args.get('lat'))
        lon = float(request.args.get('lon'))
        year, month, day = map(int, request.args.get('date').split('-'))

        tz_name = tf.timezone_at(lat=lat, lng=lon)
        if tz_name is None:
            return jsonify({"status": "error", "message": "Не удалось определить часовой пояс по координатам"}), 400

        dt = datetime(year, month, day, 12, 0, tzinfo=ZoneInfo(tz_name))
        offset_hours = dt.utcoffset().total_seconds() / 3600

        return jsonify({"status": "success", "offset": offset_hours, "tz_name": tz_name})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

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

        # Часовой пояс: по умолчанию определяем автоматически по координатам
        # места рождения (kerykeion сам учитывает исторические переходы на
        # летнее/декретное время). Если пользователь задал смещение вручную —
        # оно в приоритете (фиксированное смещение, без исторической поправки).
        manual_tz = data.get('timezone')
        if manual_tz not in (None, ''):
            tz_offset = int(manual_tz)
            tz_str = f"Etc/GMT{-tz_offset:+d}".replace("+", "")
        else:
            tz_str = tf.timezone_at(lat=lat, lng=lon)
            if tz_str is None:
                return jsonify({"status": "error", "message": "Не удалось определить часовой пояс автоматически — укажите его вручную"}), 400

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
            "neptune": "Neptune", "pluto": "Pluto", "chiron": "Chiron", "mean_lilith": "Lilith",
            "true_north_lunar_node": "Mean_Node"
        }

        for attr_name, obj_name in PLANET_MAPPING.items():
            p = getattr(subject, attr_name, None)
            if p is not None:
                planets_data.append({
                    "id": obj_name,
                    "name": PLANET_NAMES_RU.get(obj_name, obj_name),
                    "symbol": PLANET_SYMBOLS.get(obj_name, "?"),
                    "longitude": float(p.abs_pos),
                    "retrograde": bool(p.retrograde),
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
            h = getattr(subject, attr_name, None)
            if h is not None:
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

@app.route('/api/charts', methods=['GET'])
def list_charts():
    try:
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, name, birth_date, birth_time, lat, lon, place_name, "
                    "timezone_offset, gender, created_at FROM charts ORDER BY created_at DESC"
                )
                rows = cur.fetchall()
        finally:
            conn.close()
        for r in rows:
            r['birth_date'] = r['birth_date'].isoformat()
            r['birth_time'] = str(r['birth_time'])
            r['created_at'] = r['created_at'].isoformat()
        return jsonify({"status": "success", "charts": rows})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/charts', methods=['POST'])
def save_chart():
    data = request.json
    try:
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO charts (name, birth_date, birth_time, lat, lon, "
                    "place_name, timezone_offset, gender) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        data.get('name', ''), data['date'], data['time'],
                        float(data['lat']), float(data['lon']),
                        data.get('place_name', ''), float(data['timezone']),
                        data.get('gender', '')
                    )
                )
                new_id = cur.lastrowid
            conn.commit()
        finally:
            conn.close()
        return jsonify({"status": "success", "id": new_id})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/charts/<int:chart_id>', methods=['DELETE'])
def delete_chart(chart_id):
    try:
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM charts WHERE id=%s", (chart_id,))
            conn.commit()
        finally:
            conn.close()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

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