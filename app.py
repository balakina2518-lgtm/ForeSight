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

        # Новая логика для Kerykeion v4+: собираем планеты по явным атрибутам
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
                # Используем .abs_pos для координаты 360°
                planets_data.append({
                    "id": obj_name,
                    "name": PLANET_NAMES_RU.get(obj_name, obj_name),
                    "symbol": PLANET_SYMBOLS.get(obj_name, "?"),
                    "longitude": float(p.abs_pos),
                    "interpretation": INTERPRETATIONS.get(obj_name, "Описание в процессе добавления.")
                })

        # Собираем данные домов (куспидов) аналогичным образом
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
        print(f"Ошибка при расчете натальной карты: {e}") 
        return jsonify({"status": "error", "message": str(e)}), 400