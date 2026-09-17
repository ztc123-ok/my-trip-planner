"""高德不可用时读取香港天文台的九天预报。"""

from datetime import datetime
from typing import List, Tuple

import requests

from ..models.schemas import WeatherInfo


HKO_FORECAST_URL = "https://data.weather.gov.hk/weatherAPI/opendata/weather.php"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

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
            day_weather=str(forecast.get("forecastWeather", "")),
            # 天文台提供的是每日最高/最低气温，分别放入现有的日/夜温度字段。
            day_temp=maximum,
            night_temp=minimum,
            wind_direction=str(forecast.get("forecastWind", "")),
        ))
    if not result:
        raise ValueError("香港天文台预报缺少可用日期和气温")
    return result


def get_open_meteo_hong_kong_forecast() -> List[WeatherInfo]:
    """香港天文台暂不可达时，读取香港中心位置的开放气象预报。"""
    response = requests.get(OPEN_METEO_URL, params={
        "latitude": 22.3193,
        "longitude": 114.1694,
        "daily": "temperature_2m_max,temperature_2m_min,weather_code",
        "timezone": "Asia/Hong_Kong",
        "forecast_days": 10,
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
            day_weather=WMO_WEATHER.get(code, f"WMO天气代码 {code}"),
            day_temp=round(maximum),
            night_temp=round(minimum),
        ))
    if not result:
        raise ValueError("Open-Meteo 预报缺少可用日期和气温")
    return result


def get_trip_forecast(amap_service, city: str, start_date: str, end_date: str) -> Tuple[List[WeatherInfo], str]:
    """优先查询高德；香港失败时依次使用天文台和 Open-Meteo。"""
    try:
        weather = amap_service.get_weather(city)
        source = "高德地图"
    except Exception as error:
        if not is_hong_kong(city):
            raise
        print(f"高德香港天气不可用（{error}），改用香港天文台九天预报。")
        try:
            weather = get_hong_kong_forecast()
            source = "香港天文台"
        except Exception as hko_error:
            print(f"香港天文台暂不可用（{hko_error}），改用 Open-Meteo 预报。")
            weather = get_open_meteo_hong_kong_forecast()
            source = "Open-Meteo"
    return [item for item in weather if start_date <= item.date <= end_date], source
