"""Météo locale facultative via Open-Meteo, sans décision automatique de soin."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
from typing import Any

USER_AGENT = "AssistantBotanique/3 (+https://github.com/LaurentCOLL1/Assistant_Botanique)"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


@dataclass(frozen=True)
class WeatherLocation:
    name: str
    latitude: float
    longitude: float
    country: str = ""
    timezone: str = "auto"

    @property
    def label(self) -> str:
        return f"{self.name}, {self.country}" if self.country else self.name


@dataclass(frozen=True)
class WeatherDay:
    day: date
    temperature_min: float | None
    temperature_max: float | None
    precipitation_sum: float | None
    wind_gusts_max: float | None
    weather_code: int | None


class WeatherService:
    def _request(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        target = url + "?" + urllib.parse.urlencode(params, doseq=True)
        request = urllib.request.Request(
            target,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.load(response)
        if not isinstance(payload, dict):
            raise ValueError("Réponse météo invalide.")
        return payload

    def geocode(self, query: str, *, count: int = 8) -> list[WeatherLocation]:
        raw = str(query or "").strip()
        if len(raw) < 2:
            return []
        payload = self._request(
            GEOCODING_URL,
            {"name": raw, "count": max(1, min(int(count), 20)), "language": "fr", "format": "json"},
        )
        results = payload.get("results") if isinstance(payload.get("results"), list) else []
        locations = []
        for item in results:
            if not isinstance(item, dict):
                continue
            try:
                locations.append(
                    WeatherLocation(
                        name=str(item.get("name") or raw),
                        latitude=float(item["latitude"]),
                        longitude=float(item["longitude"]),
                        country=str(item.get("country") or ""),
                        timezone=str(item.get("timezone") or "auto"),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return locations

    def forecast(
        self,
        latitude: float,
        longitude: float,
        *,
        timezone: str = "auto",
        days: int = 7,
    ) -> list[WeatherDay]:
        payload = self._request(
            FORECAST_URL,
            {
                "latitude": float(latitude),
                "longitude": float(longitude),
                "timezone": timezone or "auto",
                "forecast_days": max(1, min(int(days), 16)),
                "daily": ",".join(
                    (
                        "weather_code",
                        "temperature_2m_max",
                        "temperature_2m_min",
                        "precipitation_sum",
                        "wind_gusts_10m_max",
                    )
                ),
            },
        )
        daily = payload.get("daily") if isinstance(payload.get("daily"), dict) else {}
        dates = daily.get("time") if isinstance(daily.get("time"), list) else []
        result = []
        for index, raw_day in enumerate(dates):
            try:
                parsed_day = date.fromisoformat(str(raw_day))
            except ValueError:
                continue

            def value(key: str):
                values = daily.get(key)
                if not isinstance(values, list) or index >= len(values):
                    return None
                raw = values[index]
                try:
                    return float(raw) if raw is not None else None
                except (TypeError, ValueError):
                    return None

            raw_code = value("weather_code")
            result.append(
                WeatherDay(
                    day=parsed_day,
                    temperature_min=value("temperature_2m_min"),
                    temperature_max=value("temperature_2m_max"),
                    precipitation_sum=value("precipitation_sum"),
                    wind_gusts_max=value("wind_gusts_10m_max"),
                    weather_code=int(raw_code) if raw_code is not None else None,
                )
            )
        return result


def outdoor_care_advisories(days: list[WeatherDay]) -> list[str]:
    """Produit des conseils de contrôle explicables, jamais des actions automatiques."""
    advisories: list[str] = []
    if not days:
        return advisories
    minimums = [item.temperature_min for item in days if item.temperature_min is not None]
    maximums = [item.temperature_max for item in days if item.temperature_max is not None]
    rain = sum(item.precipitation_sum or 0 for item in days[:3])
    gusts = [item.wind_gusts_max for item in days if item.wind_gusts_max is not None]
    if minimums and min(minimums) <= 3:
        advisories.append("Risque de froid : vérifier les plantes sensibles placées dehors.")
    if minimums and min(minimums) <= 0:
        advisories.append("Gel possible : protéger ou rentrer les plantes non rustiques.")
    if maximums and max(maximums) >= 32:
        advisories.append("Forte chaleur : avancer le contrôle d'humidité des pots exposés.")
    if rain >= 10:
        advisories.append("Pluie notable prévue : contrôler le drainage avant tout arrosage extérieur.")
    if gusts and max(gusts) >= 60:
        advisories.append("Rafales fortes : sécuriser les pots et tuteurs.")
    return advisories
