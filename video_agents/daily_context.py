"""Что сегодня за день: дата, погода и ветер на Кипре, фаза луны. Всё бесплатно и без ключей."""

from __future__ import annotations

import logging
import math
from datetime import date, datetime, timezone

import requests

log = logging.getLogger(__name__)

WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября",
          "ноября", "декабря"]
WIND = ["северный", "северо-восточный", "восточный", "юго-восточный", "южный", "юго-западный", "западный",
        "северо-западный"]
# Коды погоды WMO (open-meteo) - коротко по-русски.
WEATHER = {0: "ясно", 1: "почти ясно", 2: "переменная облачность", 3: "пасмурно", 45: "туман", 48: "туман",
           51: "морось", 53: "морось", 55: "морось", 61: "небольшой дождь", 63: "дождь", 65: "сильный дождь",
           80: "ливни", 81: "ливни", 82: "сильные ливни", 95: "гроза", 96: "гроза с градом", 99: "гроза с градом"}
SYNODIC_MONTH = 29.530588853
KNOWN_NEW_MOON = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)


def wind_name(degrees: float) -> str:
    return WIND[int((degrees % 360 + 22.5) // 45) % 8]


def moon_phase(moment: datetime | None = None) -> str:
    moment = moment or datetime.now(timezone.utc)
    age = ((moment - KNOWN_NEW_MOON).total_seconds() / 86400) % SYNODIC_MONTH
    phases = [(1.0, "новолуние"), (6.4, "растущий серп"), (8.4, "первая четверть"), (13.8, "растущая луна"),
              (15.8, "полнолуние"), (21.1, "убывающая луна"), (23.1, "последняя четверть"),
              (28.5, "убывающий серп"), (SYNODIC_MONTH, "новолуние")]
    return next(name for limit, name in phases if age < limit)


def weather(latitude: float, longitude: float) -> str:
    """Погода на сегодня и завтра одной строкой; пусто, если сервис недоступен."""
    try:
        response = requests.get("https://api.open-meteo.com/v1/forecast", timeout=20, params={
            "latitude": latitude, "longitude": longitude, "timezone": "auto", "forecast_days": 2,
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,"
                     "wind_speed_10m_max,wind_direction_10m_dominant"})
        response.raise_for_status()
        days = response.json()["daily"]
    except Exception as exc:  # погода - приятное дополнение, без неё тоже работаем
        log.info("Погода недоступна: %s", exc)
        return ""
    parts = []
    for i, label in enumerate(("сегодня", "завтра")):
        try:
            parts.append(
                f"{label}: {WEATHER.get(days['weather_code'][i], 'облачно')}, "
                f"{days['temperature_2m_min'][i]:.0f}..{days['temperature_2m_max'][i]:.0f}°C, "
                f"ветер {wind_name(days['wind_direction_10m_dominant'][i])} до "
                f"{days['wind_speed_10m_max'][i] / 3.6:.0f} м/с"
                + (f", осадки {days['precipitation_sum'][i]:.0f} мм" if days['precipitation_sum'][i] >= 1 else ""))
        except (KeyError, IndexError, TypeError):
            continue
    return "; ".join(parts)


def today_context(city: str, latitude: float, longitude: float, today: date | None = None) -> str:
    today = today or date.today()
    lines = [f"Сегодня {today.day} {MONTHS[today.month - 1]} {today.year}, {WEEKDAYS[today.weekday()]}."]
    forecast = weather(latitude, longitude)
    if forecast:
        lines.append(f"Погода в {city}: {forecast}.")
    lines.append(f"Луна: {moon_phase()}.")
    return "\n".join(lines)
