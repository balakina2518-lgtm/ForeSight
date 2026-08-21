from flask import Flask, request, jsonify, send_file, send_from_directory, session
from flask_cors import CORS
from kerykeion import AstrologicalSubjectFactory
from timezonefinder import TimezoneFinder
from zoneinfo import ZoneInfo
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import os
import re
import pymysql
import pymysql.cursors

app = Flask(__name__)
CORS(app, supports_credentials=True)

# Данные для подключения к БД лежат в config.py прямо на сервере (не в гите —
# файл с паролем от базы не должен попадать в публичный репозиторий). Там же —
# SECRET_KEY для подписи сессионных cookie (без него сессии слетают при
# каждом перезапуске Passenger). Импортируем раздельно: если в config.py ещё
# нет SECRET_KEY (например, не успели добавить), это не должно ронять и
# подключение к БД заодно — раньше был один try/except на всё сразу, и
# отсутствие любой из переменных обнуляло вообще все, включая DB_HOST.
try:
    from config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME
except ImportError:
    DB_HOST = DB_USER = DB_PASSWORD = DB_NAME = None
try:
    from config import SECRET_KEY
except ImportError:
    SECRET_KEY = None

app.secret_key = SECRET_KEY or 'dev-only-insecure-key-set-SECRET_KEY-in-config.py'
app.config.update(
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=True,
)

FREE_PLAN = 'free'
PAID_PLAN = 'astrolog'
FREE_CALCULATIONS_LIMIT = 1

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

def get_db_connection():
    if not DB_HOST:
        raise RuntimeError("База данных не настроена (нет config.py на сервере)")
    return pymysql.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor, charset='utf8mb4'
    )

def get_current_user(cur):
    """Текущий пользователь по сессии, либо None если не залогинен."""
    user_id = session.get('user_id')
    if not user_id:
        return None
    cur.execute("SELECT id, email, plan, calculations_used FROM users WHERE id=%s", (user_id,))
    return cur.fetchone()

tf = TimezoneFinder()

# Карта символов для планет
PLANET_SYMBOLS = {
    "Sun": "☉", "Moon": "☽", "Mercury": "☿", "Venus": "♀",
    "Mars": "♂", "Jupiter": "♃", "Saturn": "♄", "Uranus": "♅",
    "Neptune": "♆", "Pluto": "♇", "Chiron": "⚷", "Lilith": "⚸",
    "Mean_Node": "☊", "South_Node": "☋"
}

# Словарь для перевода названий на русский язык
PLANET_NAMES_RU = {
    "Sun": "Солнце", "Moon": "Луна", "Mercury": "Меркурий", "Venus": "Венера",
    "Mars": "Марс", "Jupiter": "Юпитер", "Saturn": "Сатурн", "Uranus": "Уран",
    "Neptune": "Нептун", "Pluto": "Плутон", "Chiron": "Хирон", "Lilith": "Лилит",
    "Mean_Node": "Северный Узел", "South_Node": "Южный Узел"
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
    "Mean_Node": "Северный Узел указывает на вектор вашего стратегического развития, эволюционную задачу и новые горизонты в карьере.",
    "South_Node": "Южный Узел показывает накопленный опыт и зону комфорта — то, от чего важно оттолкнуться на пути к задачам Северного Узла."
}

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    if not EMAIL_RE.match(email):
        return jsonify({"status": "error", "message": "Некорректный email"}), 400
    if len(password) < 6:
        return jsonify({"status": "error", "message": "Пароль должен быть не короче 6 символов"}), 400
    if not data.get('consent'):
        return jsonify({"status": "error", "message": "Нужно согласие на обработку персональных данных"}), 400
    try:
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM users WHERE email=%s", (email,))
                if cur.fetchone():
                    return jsonify({"status": "error", "message": "Пользователь с таким email уже зарегистрирован"}), 400
                cur.execute(
                    "INSERT INTO users (email, password_hash, plan) VALUES (%s, %s, %s)",
                    (email, generate_password_hash(password), FREE_PLAN)
                )
                user_id = cur.lastrowid
            conn.commit()
        finally:
            conn.close()
        session['user_id'] = user_id
        return jsonify({"status": "success", "email": email, "plan": FREE_PLAN})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    try:
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id, email, password_hash, plan FROM users WHERE email=%s", (email,))
                user = cur.fetchone()
        finally:
            conn.close()
        if not user or not check_password_hash(user['password_hash'], password):
            return jsonify({"status": "error", "message": "Неверный email или пароль"}), 401
        session['user_id'] = user['id']
        return jsonify({"status": "success", "email": user['email'], "plan": user['plan']})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    return jsonify({"status": "success"})

@app.route('/api/me', methods=['GET'])
def me():
    try:
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                user = get_current_user(cur)
        finally:
            conn.close()
        if not user:
            return jsonify({"status": "success", "user": None, "anon": {
                "calculations_used": session.get('anon_calculations_used', 0),
                "calculations_limit": FREE_CALCULATIONS_LIMIT
            }})
        return jsonify({"status": "success", "user": {
            "email": user['email'],
            "plan": user['plan'],
            "calculations_used": user['calculations_used'],
            "calculations_limit": FREE_CALCULATIONS_LIMIT if user['plan'] == FREE_PLAN else None
        }})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

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

PLANET_MAPPING = {
    "sun": "Sun", "moon": "Moon", "mercury": "Mercury", "venus": "Venus",
    "mars": "Mars", "jupiter": "Jupiter", "saturn": "Saturn", "uranus": "Uranus",
    "neptune": "Neptune", "pluto": "Pluto", "chiron": "Chiron", "mean_lilith": "Lilith",
    "true_north_lunar_node": "Mean_Node", "true_south_lunar_node": "South_Node"
}
HOUSE_MAPPING = [
    "first_house", "second_house", "third_house", "fourth_house",
    "fifth_house", "sixth_house", "seventh_house", "eighth_house",
    "ninth_house", "tenth_house", "eleventh_house", "twelfth_house"
]

# Буквенные коды систем домов — из документации Kerykeion (Swiss Ephemeris):
# P=Placidus, R=Regiomontanus, K=Koch, A=equal (Равнодомная)
HOUSE_SYSTEM_CODES = {"placidus": "P", "regiomontanus": "R", "koch": "K", "equal": "A"}

def build_chart_payload(name, year, month, day, hour, minute, lat, lon, tz_str,
                         houses_system_identifier='P', seconds=0):
    """Общая логика построения планет/домов через Kerykeion — используется и
    обычным расчётом (/api/calculate), и картой дня (/api/daily-chart)."""
    subject = AstrologicalSubjectFactory.from_birth_data(
        name=name,
        year=year, month=month, day=day,
        hour=hour, minute=minute,
        lng=lon, lat=lat,
        tz_str=tz_str,
        online=False,
        houses_system_identifier=houses_system_identifier,
        seconds=seconds
    )

    planets_data = []
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

    houses_data = []
    for i, attr_name in enumerate(HOUSE_MAPPING, start=1):
        h = getattr(subject, attr_name, None)
        if h is not None:
            houses_data.append({
                "num": i,
                "name": f"{i} Дом",
                "longitude": float(h.abs_pos)
            })

    return {"planets": planets_data, "houses": houses_data}

@app.route('/api/daily-chart', methods=['GET'])
def daily_chart():
    """Карта дня — дата и город всегда сегодня/Москва, без входа и без
    лимитов (пробник, не расходует ничей бесплатный лимит — по прямому
    уточнению Елены, ограничения только на тарифах). Время по умолчанию —
    текущее, но можно передать своё через ?time=ЧЧ:ММ (дату/город всё равно
    не поменять — этот эндпоинт всегда строит на сегодня и Москву)."""
    try:
        moscow_tz = ZoneInfo('Europe/Moscow')
        now = datetime.now(moscow_tz)
        hour, minute = now.hour, now.minute
        time_param = request.args.get('time')
        if time_param:
            hour, minute = map(int, time_param.split(':'))
        result = build_chart_payload(
            name='Карта дня',
            year=now.year, month=now.month, day=now.day,
            hour=hour, minute=minute,
            lat=55.7558, lon=37.6176, tz_str='Europe/Moscow'
        )
        return jsonify({"status": "success", **result})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/calculate', methods=['POST', 'OPTIONS'])
def calculate():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200

    data = request.json
    try:
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                current_user = get_current_user(cur)
        finally:
            conn.close()
        if current_user:
            if current_user['plan'] == FREE_PLAN and current_user['calculations_used'] >= FREE_CALCULATIONS_LIMIT:
                return jsonify({"status": "error", "message": "Бесплатный тариф позволяет построить только 1 карту. Оформите тариф «Сам себе астролог» для неограниченного доступа."}), 403
        else:
            # Без регистрации — тоже 1 бесплатная карта, счётчик живёт в сессии
            # (без привязки к аккаунту, карта нигде не сохраняется)
            if session.get('anon_calculations_used', 0) >= FREE_CALCULATIONS_LIMIT:
                return jsonify({"status": "error", "message": "Бесплатная карта без регистрации уже использована. Зарегистрируйтесь, чтобы построить ещё одну."}), 403
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    try:
        # Явные проверки перед парсингом — иначе int('') на пустой дате/времени
        # даёт малопонятную ошибку "invalid literal for int() with base 10: ''"
        # без указания, какое именно поле пустое
        if not data.get('date'):
            return jsonify({"status": "error", "message": "Не указана дата рождения"}), 400
        if not data.get('time'):
            return jsonify({"status": "error", "message": "Не указано время рождения"}), 400

        # Парсим дату и время
        year, month, day = map(int, data['date'].split('-'))
        hour, minute = map(int, data['time'].split(':'))
        second = int(data.get('second') or 0)

        lat = float(data['lat'])
        lon = float(data['lon'])

        house_system_code = HOUSE_SYSTEM_CODES.get(data.get('house_system'), 'P')

        # Часовой пояс: по умолчанию определяем автоматически по координатам
        # места рождения (kerykeion сам учитывает исторические переходы на
        # летнее/декретное время). Если пользователь задал смещение вручную —
        # оно в приоритете (фиксированное смещение, без исторической поправки).
        manual_tz = data.get('timezone')
        if manual_tz not in (None, '') and str(manual_tz).strip() != '':
            tz_offset = int(manual_tz)
            tz_str = f"Etc/GMT{-tz_offset:+d}".replace("+", "")
        else:
            tz_str = tf.timezone_at(lat=lat, lng=lon)
            if tz_str is None:
                return jsonify({"status": "error", "message": "Не удалось определить часовой пояс автоматически — укажите его вручную"}), 400

        result = build_chart_payload(
            data.get('name', 'Проект'), year, month, day, hour, minute, lat, lon, tz_str,
            houses_system_identifier=house_system_code, seconds=second
        )

        # Каталог объектов — какие из уже посчитанных тел реально показывать.
        # Список приходит с фронта (id из PLANET_MAPPING); если не передан —
        # ничего не фильтруем, ведут себя как раньше (все тела показаны).
        active_points = data.get('active_points')
        if active_points:
            active_set = set(active_points)
            result = {**result, "planets": [p for p in result["planets"] if p["id"] in active_set]}

        if current_user:
            if current_user['plan'] == FREE_PLAN:
                conn = get_db_connection()
                try:
                    with conn.cursor() as cur:
                        cur.execute("UPDATE users SET calculations_used = calculations_used + 1 WHERE id=%s", (current_user['id'],))
                    conn.commit()
                finally:
                    conn.close()
        else:
            session['anon_calculations_used'] = session.get('anon_calculations_used', 0) + 1

        return jsonify({"status": "success", **result})

    except Exception as e:
        print(f"Ошибка при расчете: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/api/charts', methods=['GET'])
def list_charts():
    try:
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                current_user = get_current_user(cur)
                if not current_user:
                    return jsonify({"status": "error", "message": "Войдите, чтобы посмотреть библиотеку карт"}), 401
                # Бесплатный тариф карты не хранит — библиотека всегда пуста
                if current_user['plan'] == FREE_PLAN:
                    return jsonify({"status": "success", "charts": []})
                cur.execute(
                    "SELECT id, name, birth_date, birth_time, lat, lon, place_name, "
                    "timezone_offset, gender, chart_type, comment, folder_id, created_at FROM charts "
                    "WHERE user_id=%s ORDER BY created_at DESC",
                    (current_user['id'],)
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
    name = (data.get('name') or '').strip()
    try:
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                current_user = get_current_user(cur)
                if not current_user:
                    return jsonify({"status": "error", "message": "Войдите, чтобы сохранить карту"}), 401
                if current_user['plan'] == FREE_PLAN:
                    return jsonify({"status": "error", "message": "Сохранение карт в библиотеку доступно на тарифе «Сам себе астролог»"}), 403

                # Карта с таким же названием у ЭТОГО пользователя уже есть —
                # обновляем её вместо дубля. Безымянные карты (пустое название)
                # не дедуплицируются между собой. Карты других пользователей не
                # затрагиваются, даже при совпадении названия.
                existing_id = None
                if name:
                    cur.execute("SELECT id FROM charts WHERE name=%s AND user_id=%s LIMIT 1", (name, current_user['id']))
                    existing = cur.fetchone()
                    if existing:
                        existing_id = existing['id']

                folder_id = data.get('folder_id')
                folder_id = int(folder_id) if folder_id not in (None, '') else None
                if folder_id is not None:
                    # Папка должна принадлежать этому же пользователю — иначе тихо игнорируем
                    cur.execute("SELECT id FROM folders WHERE id=%s AND user_id=%s", (folder_id, current_user['id']))
                    if not cur.fetchone():
                        folder_id = None

                if existing_id:
                    if 'folder_id' in data:
                        cur.execute(
                            "UPDATE charts SET birth_date=%s, birth_time=%s, lat=%s, lon=%s, "
                            "place_name=%s, timezone_offset=%s, gender=%s, chart_type=%s, folder_id=%s WHERE id=%s AND user_id=%s",
                            (
                                data['date'], data['time'], float(data['lat']), float(data['lon']),
                                data.get('place_name', ''), float(data['timezone']),
                                data.get('gender', ''), data.get('chart_type', 'natal'), folder_id,
                                existing_id, current_user['id']
                            )
                        )
                    else:
                        # folder_id не передан — обновляем карту, не трогая её текущую папку
                        cur.execute(
                            "UPDATE charts SET birth_date=%s, birth_time=%s, lat=%s, lon=%s, "
                            "place_name=%s, timezone_offset=%s, gender=%s, chart_type=%s WHERE id=%s AND user_id=%s",
                            (
                                data['date'], data['time'], float(data['lat']), float(data['lon']),
                                data.get('place_name', ''), float(data['timezone']),
                                data.get('gender', ''), data.get('chart_type', 'natal'),
                                existing_id, current_user['id']
                            )
                        )
                    new_id = existing_id
                else:
                    cur.execute(
                        "INSERT INTO charts (user_id, name, birth_date, birth_time, lat, lon, "
                        "place_name, timezone_offset, gender, chart_type, comment, folder_id) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (
                            current_user['id'], name, data['date'], data['time'],
                            float(data['lat']), float(data['lon']),
                            data.get('place_name', ''), float(data['timezone']),
                            data.get('gender', ''), data.get('chart_type', 'natal'),
                            data.get('comment', ''), folder_id
                        )
                    )
                    new_id = cur.lastrowid
            conn.commit()
        finally:
            conn.close()
        return jsonify({"status": "success", "id": new_id})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/charts/<int:chart_id>/comment', methods=['PATCH'])
def update_chart_comment(chart_id):
    data = request.json
    try:
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                current_user = get_current_user(cur)
                if not current_user:
                    return jsonify({"status": "error", "message": "Войдите в аккаунт"}), 401
                cur.execute(
                    "UPDATE charts SET comment=%s WHERE id=%s AND user_id=%s",
                    (data.get('comment', ''), chart_id, current_user['id'])
                )
            conn.commit()
        finally:
            conn.close()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/charts/<int:chart_id>/folder', methods=['PATCH'])
def update_chart_folder(chart_id):
    data = request.json or {}
    try:
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                current_user = get_current_user(cur)
                if not current_user:
                    return jsonify({"status": "error", "message": "Войдите в аккаунт"}), 401
                folder_id = data.get('folder_id')
                folder_id = int(folder_id) if folder_id not in (None, '') else None
                if folder_id is not None:
                    cur.execute("SELECT id FROM folders WHERE id=%s AND user_id=%s", (folder_id, current_user['id']))
                    if not cur.fetchone():
                        return jsonify({"status": "error", "message": "Папка не найдена"}), 404
                cur.execute(
                    "UPDATE charts SET folder_id=%s WHERE id=%s AND user_id=%s",
                    (folder_id, chart_id, current_user['id'])
                )
            conn.commit()
        finally:
            conn.close()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/folders', methods=['GET'])
def list_folders():
    try:
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                current_user = get_current_user(cur)
                if not current_user:
                    return jsonify({"status": "error", "message": "Войдите в аккаунт"}), 401
                cur.execute("SELECT id, name FROM folders WHERE user_id=%s ORDER BY name", (current_user['id'],))
                rows = cur.fetchall()
        finally:
            conn.close()
        return jsonify({"status": "success", "folders": rows})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/folders', methods=['POST'])
def create_folder():
    data = request.json or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({"status": "error", "message": "Введите название папки"}), 400
    try:
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                current_user = get_current_user(cur)
                if not current_user:
                    return jsonify({"status": "error", "message": "Войдите в аккаунт"}), 401
                cur.execute("INSERT INTO folders (user_id, name) VALUES (%s, %s)", (current_user['id'], name))
                new_id = cur.lastrowid
            conn.commit()
        finally:
            conn.close()
        return jsonify({"status": "success", "id": new_id, "name": name})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/folders/<int:folder_id>', methods=['PATCH'])
def rename_folder(folder_id):
    data = request.json or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({"status": "error", "message": "Введите название папки"}), 400
    try:
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                current_user = get_current_user(cur)
                if not current_user:
                    return jsonify({"status": "error", "message": "Войдите в аккаунт"}), 401
                cur.execute("UPDATE folders SET name=%s WHERE id=%s AND user_id=%s", (name, folder_id, current_user['id']))
            conn.commit()
        finally:
            conn.close()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/folders/<int:folder_id>', methods=['DELETE'])
def delete_folder(folder_id):
    try:
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                current_user = get_current_user(cur)
                if not current_user:
                    return jsonify({"status": "error", "message": "Войдите в аккаунт"}), 401
                # Карты из удаляемой папки не удаляются — просто становятся "без папки"
                cur.execute("UPDATE charts SET folder_id=NULL WHERE folder_id=%s AND user_id=%s", (folder_id, current_user['id']))
                cur.execute("DELETE FROM folders WHERE id=%s AND user_id=%s", (folder_id, current_user['id']))
            conn.commit()
        finally:
            conn.close()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/charts/<int:chart_id>', methods=['DELETE'])
def delete_chart(chart_id):
    try:
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                current_user = get_current_user(cur)
                if not current_user:
                    return jsonify({"status": "error", "message": "Войдите в аккаунт"}), 401
                cur.execute("DELETE FROM charts WHERE id=%s AND user_id=%s", (chart_id, current_user['id']))
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

@app.route('/policy', methods=['GET'])
def policy():
    try:
        return send_file('policy.html')
    except Exception as e:
        return f"Ошибка сервера: {e}", 500

# Картинки планет для витрины на стартовом экране входа/регистрации.
# send_from_directory защищает от выхода за пределы папки planets/.
@app.route('/planets/<path:filename>', methods=['GET'])
def planet_image(filename):
    try:
        return send_from_directory('planets', filename)
    except Exception as e:
        return f"Ошибка сервера: {e}", 500

if __name__ == '__main__':
    app.run()