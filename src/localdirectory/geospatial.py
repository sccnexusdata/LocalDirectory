from __future__ import annotations

from math import asin, cos, radians, sin, sqrt


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0088
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * radius * asin(sqrt(a))


def within_radius(
    latitude: float | None,
    longitude: float | None,
    centre_latitude: float,
    centre_longitude: float,
    radius_km: float,
) -> bool:
    if latitude is None or longitude is None:
        return False
    return haversine_km(centre_latitude, centre_longitude, latitude, longitude) <= radius_km
