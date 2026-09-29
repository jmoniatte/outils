"""Sunrise, sunset and the full moon on any day, worked out here: no request, past or future.

Sunrise and sunset use the sunrise equation (a minute or two off, enough for a calendar); the full
moon, Meeus's formula (a few minutes off).
"""

import math
from datetime import date, datetime, timedelta, timezone, tzinfo
from typing import NamedTuple

J2000 = 2451545.0
# The ordinal of 2000-01-01, the day J2000 falls on (at noon UTC)
J2000_ORDINAL = date(2000, 1, 1).toordinal()
# Where the sun's middle is when its top edge meets the horizon, air's bending included
HORIZON = -0.833
TILT = 23.4397

SYNODIC_MONTH = 29.530588861
# Nerd Font's crescent, as the Weather tab has for a clear night: it reads as the moon, the words say which
FULL_MOON = "\U000f0594"


class Sun(NamedTuple):
    # None both when the sun never sets or never rises that day, near the poles
    rise: datetime | None
    set: datetime | None


def sun(day: date, latitude: float, longitude: float, zone: tzinfo) -> Sun:
    """When the sun rises and sets on day where latitude and longitude say, in zone's time."""
    # Days from J2000 to that day's solar noon there, east longitudes positive
    days = day.toordinal() - J2000_ORDINAL - longitude / 360
    anomaly = math.radians((357.5291 + 0.98560028 * days) % 360)
    centre = 1.9148 * math.sin(anomaly) + 0.02 * math.sin(2 * anomaly) + 0.0003 * math.sin(3 * anomaly)
    ecliptic = math.radians((math.degrees(anomaly) + centre + 180 + 102.9372) % 360)
    noon = J2000 + days + 0.0053 * math.sin(anomaly) - 0.0069 * math.sin(2 * ecliptic)
    declination = math.asin(math.sin(ecliptic) * math.sin(math.radians(TILT)))
    latitude = math.radians(latitude)
    cos_hour = (math.sin(math.radians(HORIZON)) - math.sin(latitude) * math.sin(declination)) / (
        math.cos(latitude) * math.cos(declination)
    )
    if not -1 <= cos_hour <= 1:
        return Sun(None, None)
    half = math.degrees(math.acos(cos_hour)) / 360
    return Sun(_local(noon - half, zone), _local(noon + half, zone))


def _local(julian: float, zone: tzinfo) -> datetime:
    return (datetime(2000, 1, 1, 12, tzinfo=timezone.utc) + timedelta(days=julian - J2000)).astimezone(zone)


def full_moon(day: date, zone: tzinfo | None = None) -> bool:
    """Whether the moon is full on day, in zone's time, the system's by default."""
    # The full moons nearest the day, counted from the first new moon of 2000
    near = round((day.toordinal() - J2000_ORDINAL) / SYNODIC_MONTH)
    return any(_full_moon(k + 0.5).astimezone(zone).date() == day for k in range(near - 1, near + 1))


def _full_moon(k: float) -> datetime:
    """When full moon k is, by Meeus's Astronomical Algorithms (chapter 49), its largest terms."""
    t = k / 1236.85
    julian = 2451550.09766 + SYNODIC_MONTH * k + 0.00015437 * t * t
    e = 1 - 0.002516 * t - 0.0000074 * t * t
    sun_anomaly = math.radians(2.5534 + 29.10535670 * k)
    anomaly = math.radians(201.5643 + 385.81693528 * k + 0.0107582 * t * t)
    latitude = math.radians(160.7108 + 390.67050284 * k - 0.0016118 * t * t)
    node = math.radians(124.7746 - 1.56375588 * k)
    julian += (
        -0.40614 * math.sin(anomaly)
        + 0.17302 * e * math.sin(sun_anomaly)
        + 0.01614 * math.sin(2 * anomaly)
        + 0.01043 * math.sin(2 * latitude)
        + 0.00734 * e * math.sin(anomaly - sun_anomaly)
        - 0.00515 * e * math.sin(anomaly + sun_anomaly)
        + 0.00209 * e * e * math.sin(2 * sun_anomaly)
        - 0.00111 * math.sin(anomaly - 2 * latitude)
        - 0.00057 * math.sin(anomaly + 2 * latitude)
        + 0.00056 * e * math.sin(2 * anomaly + sun_anomaly)
        - 0.00042 * math.sin(3 * anomaly)
        + 0.00042 * e * math.sin(sun_anomaly + 2 * latitude)
        + 0.00038 * e * math.sin(sun_anomaly - 2 * latitude)
        - 0.00024 * e * math.sin(2 * anomaly - sun_anomaly)
        - 0.00017 * math.sin(node)
    )
    return _local(julian, timezone.utc)
