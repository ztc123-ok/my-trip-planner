"""按行程日期合并短期高德预报与更长时段的可靠预报。"""

from datetime import date, datetime, timedelta
from typing import List, Tuple

import requests

from ..models.schemas import WeatherInfo


HKO_FORECAST_URL = "https://data.weather.gov.hk/weatherAPI/opendata/weather.php"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

WMO_WEATHER = {
    0: "晴", 1: "大致晴", 2: "局部多云", 3: "阴",
    45: "有雾", 48: "雾凇", 51: "小毛毛雨", 53: "毛毛雨", 55: "大毛毛雨",
    56: "冻毛毛雨", 57: "较强冻毛毛雨", 61: "小雨", 63: "中雨", 65: "大雨",
    66: "冻雨", 67: "较强冻雨", 71: "小雪", 73: "中雪", 75: "大雪",
    77: "雪粒", 80: "小阵雨", 81: "阵雨", 82: "大阵雨",
    85: "小阵雪", 86: "大阵雪", 95: "雷雨", 96: "雷雨伴小冰雹", 99: "雷雨伴大冰雹",
}


def is_hong_kong(city: str) -> bool:
    return city.strip().casefold() in {
        "香港", "香港特别行政区", "香港特別行政區", "hong kong", "hongkong"
    }


def get_hong_kong_forecast() -> List[WeatherInfo]:
    """将香港天文台九天预报转换为项目天气模型。"""
    for attempt in range(2):
        try:
            response = requests.get(
                HKO_FORECAST_URL,
                params={"dataType": "fnd", "lang": "sc"},
                timeout=(5, 20),
            )
            response.raise_for_status()
            break
        except requests.RequestException:
            if attempt:
                raise
    forecasts = response.json().get("weatherForecast")
    if not isinstance(forecasts, list) or not forecasts:
        raise ValueError("香港天文台未返回九天预报")

    result = []
    for forecast in forecasts:
        if not isinstance(forecast, dict):
            continue
        try:
            date = datetime.strptime(forecast["forecastDate"], "%Y%m%d").date().isoformat()
            maximum = forecast["forecastMaxtemp"]["value"]
            minimum = forecast["forecastMintemp"]["value"]
        except (KeyError, TypeError, ValueError):
            continue
        result.append(WeatherInfo(
            date=date,
            source="香港天文台",
            day_weather=str(forecast.get("forecastWeather", "")),
            # 天文台提供的是每日最高/最低气温，分别放入现有的日/夜温度字段。
            day_temp=maximum,
            night_temp=minimum,
            wind_direction=str(forecast.get("forecastWind", "")),
        ))
    if not result:
        raise ValueError("香港天文台预报缺少可用日期和气温")
    return result


def _get_open_meteo_forecast(latitude: float, longitude: float, timezone: str) -> List[WeatherInfo]:
    response = requests.get(OPEN_METEO_URL, params={
        "latitude": latitude,
        "longitude": longitude,
        "daily": "temperature_2m_max,temperature_2m_min,weather_code",
        "timezone": timezone,
        "forecast_days": 16,
    }, timeout=15)
    response.raise_for_status()
    daily = response.json().get("daily")
    if not isinstance(daily, dict):
        raise ValueError("Open-Meteo 未返回每日预报")
    result = []
    for date, maximum, minimum, code in zip(
        daily.get("time", []), daily.get("temperature_2m_max", []),
        daily.get("temperature_2m_min", []), daily.get("weather_code", []),
    ):
        if not date or maximum is None or minimum is None or code is None:
            continue
        result.append(WeatherInfo(
            date=date,
            source="Open-Meteo",
            day_weather=WMO_WEATHER.get(code, f"WMO天气代码 {code}"),
            day_temp=round(maximum),
            night_temp=round(minimum),
        ))
    if not result:
        raise ValueError("Open-Meteo 预报缺少可用日期和气温")
    return result


def get_open_meteo_hong_kong_forecast() -> List[WeatherInfo]:
    """香港天文台暂不可达时，读取香港中心位置的开放气象预报。"""
    return _get_open_meteo_forecast(22.3193, 114.1694, "Asia/Hong_Kong")


def get_open_meteo_forecast(city: str) -> List[WeatherInfo]:
    """先用 Open-Meteo 地名服务确定城市，再查询当地日期的每日预报。"""
    # 地名服务按“杭州”可找到城市，但“杭州市”可能无结果或匹配到同名地点。
    place_name = city.strip().removesuffix("市")
    response = requests.get(
        OPEN_METEO_GEOCODING_URL,
        params={"name": place_name, "count": 10, "language": "zh"},
        timeout=15,
    )
    response.raise_for_status()
    locations = response.json().get("results")
    if not isinstance(locations, list) or not locations:
        raise ValueError(f"Open-Meteo 未找到城市：{city}")
    candidates = [item for item in locations if item.get("name") == place_name]
    if not candidates:
        raise ValueError(f"Open-Meteo 无法准确定位城市：{city}")
    candidates.sort(key=lambda item: item.get("population") or 0, reverse=True)
    if len(candidates) > 1 and not candidates[0].get("population"):
        raise ValueError(f"Open-Meteo 找到多个同名地点，请补充目的地信息：{city}")
    location = candidates[0]
    return _get_open_meteo_forecast(
        float(location["latitude"]), float(location["longitude"]),
        str(location.get("timezone") or "auto"),
    )


def _trip_dates(start_date: str, end_date: str) -> set[str]:
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    return {(start + timedelta(days=offset)).isoformat()
            for offset in range((end - start).days + 1)}


def get_trip_forecast(amap_service, city: str, start_date: str, end_date: str) -> Tuple[List[WeatherInfo], str]:
    """优先使用高德，按需用较长时段的预报补齐行程日期。"""
    requested_dates = _trip_dates(start_date, end_date)
    try:
        weather = amap_service.get_weather(city)
        source = "高德地图"
    except Exception as error:
        if is_hong_kong(city):
            print(f"高德香港天气不可用（{error}），改用香港天文台九天预报。")
            try:
                weather = get_hong_kong_forecast()
                source = "香港天文台"
            except Exception as hko_error:
                print(f"香港天文台暂不可用（{hko_error}），改用 Open-Meteo 预报。")
                weather = get_open_meteo_hong_kong_forecast()
                source = "Open-Meteo"
        else:
            print(f"高德天气不可用（{error}），改用 Open-Meteo 预报。")
            weather = get_open_meteo_forecast(city)
            source = "Open-Meteo"

    by_date = {item.date: item for item in weather if item.date in requested_dates}
    supplements = []
    if source != "Open-Meteo":
        if is_hong_kong(city):
            if source == "高德地图":
                supplements.append(("香港天文台", get_hong_kong_forecast))
            supplements.append(("Open-Meteo", get_open_meteo_hong_kong_forecast))
        else:
            supplements.append(("Open-Meteo", lambda: get_open_meteo_forecast(city)))
    for supplement_source, fetch in supplements:
        if not requested_dates - by_date.keys():
            break
        try:
            supplement = fetch()
            added = False
            for item in supplement:
                if item.date in requested_dates and item.date not in by_date:
                    by_date[item.date] = item
                    added = True
            if added:
                source += f" + {supplement_source}"
        except (requests.RequestException, ValueError, KeyError, TypeError) as supplement_error:
            print(f"{supplement_source} 补充预报不可用：{supplement_error}")
    return [by_date[day] for day in sorted(by_date)], source
