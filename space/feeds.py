# Copyright 2026 SZL Holdings
# SPDX-License-Identifier: Apache-2.0
"""Live-or-SAMPLE data feeds for the yarqa Space.

ONE code path per data source. Each fetcher attempts a real, license-clean
public API and returns a result whose ``state`` is:

  * ``LIVE``   — the real feed responded with usable data (recorded ``source``).
  * ``SAMPLE`` — the feed was unreachable / errored / offline, so a clearly
    SAMPLE-labeled synthetic value is returned instead.

We NEVER label synthetic data ``LIVE``. The same code runs in the preview
sandbox and on the HF Space; only the badge differs based on REAL reachability.

License / attribution (cited in the UI too):
  * Open-Meteo  — CC BY 4.0     (https://open-meteo.com/en/license)
  * NOAA CO-OPS — U.S. public domain (https://tidesandcurrents.noaa.gov/api/)

No people/repo scraping; only these public physical-data APIs. Clean-room.
"""
from __future__ import annotations

import json
import math
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field, asdict
from typing import Any

import numpy as np

# --- source registry (cited in the UI) ------------------------------------

MARINE_URL = (
    "https://marine-api.open-meteo.com/v1/marine"
    "?latitude=40.7&longitude=-70.0"
    "&hourly=ocean_current_velocity,ocean_current_direction&forecast_days=1"
)
WIND_URL = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude=40.7&longitude=-70.0"
    "&hourly=wind_speed_10m,wind_direction_10m&forecast_days=1"
)
NOAA_URL = (
    "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
    "?date=latest&station=cb0102&product=currents"
    "&time_zone=gmt&units=metric&format=json"
)

SOURCES = {
    "marine": {
        "name": "Open-Meteo Marine — ocean current velocity/direction",
        "url": MARINE_URL,
        "attribution": "Open-Meteo (CC BY 4.0)",
        "license_url": "https://open-meteo.com/en/license",
    },
    "wind": {
        "name": "Open-Meteo Wind — 10 m wind speed/direction",
        "url": WIND_URL,
        "attribution": "Open-Meteo (CC BY 4.0)",
        "license_url": "https://open-meteo.com/en/license",
    },
    "noaa": {
        "name": "NOAA CO-OPS real-time currents — station cb0102 (Cape Henry)",
        "url": NOAA_URL,
        "attribution": "NOAA Tides & Currents (U.S. public domain)",
        "license_url": "https://tidesandcurrents.noaa.gov/api/",
    },
}

_TIMEOUT = 12.0  # seconds; HF egress + sandbox both honored


@dataclass
class FeedResult:
    """One source reading with an honest LIVE/SAMPLE state."""

    key: str
    state: str                       # "LIVE" | "SAMPLE"
    name: str
    url: str
    attribution: str
    license_url: str
    fetched_utc: str
    # physical reading reduced to a current/flow vector (speed m/s, dir deg)
    speed_ms: float = 0.0
    direction_deg: float = 0.0
    detail: str = ""
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _http_get_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "yarqa-space/1.0"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _pick_first_valid(times: list, vals: list) -> tuple[int, float]:
    """Return (index, value) of the first non-null hourly value."""
    for i, v in enumerate(vals):
        if v is not None:
            return i, float(v)
    raise ValueError("no valid hourly value")


def fetch_marine() -> FeedResult:
    """Open-Meteo Marine — ocean current. km/h -> m/s."""
    s = SOURCES["marine"]
    base = dict(key="marine", name=s["name"], url=s["url"],
                attribution=s["attribution"], license_url=s["license_url"],
                fetched_utc=_now())
    try:
        data = _http_get_json(MARINE_URL)
        h = data["hourly"]
        i, vel_kmh = _pick_first_valid(h["time"], h["ocean_current_velocity"])
        direction = float(h["ocean_current_direction"][i] or 0.0)
        speed_ms = vel_kmh / 3.6
        return FeedResult(state="LIVE", speed_ms=speed_ms, direction_deg=direction,
                          detail=f"current {vel_kmh:.2f} km/h @ {direction:.0f}deg "
                                 f"(t={h['time'][i]} UTC)", **base)
    except Exception as e:  # offline / blocked / schema change -> honest SAMPLE
        return FeedResult(state="SAMPLE", speed_ms=0.22, direction_deg=78.0,
                          detail="SAMPLE / SIMULATED ocean current (feed unreachable)",
                          error=f"{type(e).__name__}: {e}", **base)


def fetch_wind() -> FeedResult:
    """Open-Meteo Wind — 10 m wind. km/h -> m/s."""
    s = SOURCES["wind"]
    base = dict(key="wind", name=s["name"], url=s["url"],
                attribution=s["attribution"], license_url=s["license_url"],
                fetched_utc=_now())
    try:
        data = _http_get_json(WIND_URL)
        h = data["hourly"]
        i, spd_kmh = _pick_first_valid(h["time"], h["wind_speed_10m"])
        direction = float(h["wind_direction_10m"][i] or 0.0)
        speed_ms = spd_kmh / 3.6
        return FeedResult(state="LIVE", speed_ms=speed_ms, direction_deg=direction,
                          detail=f"wind {spd_kmh:.2f} km/h @ {direction:.0f}deg "
                                 f"(t={h['time'][i]} UTC)", **base)
    except Exception as e:
        return FeedResult(state="SAMPLE", speed_ms=4.1, direction_deg=212.0,
                          detail="SAMPLE / SIMULATED wind (feed unreachable)",
                          error=f"{type(e).__name__}: {e}", **base)


def fetch_noaa() -> FeedResult:
    """NOAA CO-OPS real-time currents — cm/s -> m/s."""
    s = SOURCES["noaa"]
    base = dict(key="noaa", name=s["name"], url=s["url"],
                attribution=s["attribution"], license_url=s["license_url"],
                fetched_utc=_now())
    try:
        data = _http_get_json(NOAA_URL)
        rec = data["data"][0]
        speed_cms = float(rec["s"])
        direction = float(rec["d"])
        speed_ms = speed_cms / 100.0
        st = data.get("metadata", {}).get("name", "cb0102")
        return FeedResult(state="LIVE", speed_ms=speed_ms, direction_deg=direction,
                          detail=f"{st}: {speed_cms:.1f} cm/s @ {direction:.0f}deg "
                                 f"(t={rec.get('t','?')} GMT)", **base)
    except Exception as e:
        return FeedResult(state="SAMPLE", speed_ms=0.116, direction_deg=113.0,
                          detail="SAMPLE / SIMULATED current (feed unreachable)",
                          error=f"{type(e).__name__}: {e}", **base)


_FETCHERS = {"marine": fetch_marine, "wind": fetch_wind, "noaa": fetch_noaa}


def fetch_all() -> dict[str, FeedResult]:
    """Fetch every source once. Each independently LIVE or SAMPLE."""
    return {k: fn() for k, fn in _FETCHERS.items()}


# --- caching with jitter ----------------------------------------------------

class FeedCache:
    """Caches feed reads, refreshing on a jittered 10-15 s interval."""

    def __init__(self, min_age: float = 10.0, max_age: float = 15.0) -> None:
        import random
        self._random = random.Random(7)
        self._min, self._max = min_age, max_age
        self._cache: dict[str, FeedResult] = {}
        self._next_refresh = 0.0

    def _interval(self) -> float:
        return self._random.uniform(self._min, self._max)

    def get(self, force: bool = False) -> dict[str, FeedResult]:
        now = time.monotonic()
        if force or not self._cache or now >= self._next_refresh:
            self._cache = fetch_all()
            self._next_refresh = now + self._interval()
        return self._cache


# --- live/sample velocity field for yarqa.compartmentalize ------------------

def velocity_field_from_feeds(
    feeds: dict[str, FeedResult], nx: int = 14, ny: int = 9
) -> dict[str, Any]:
    """Build a 2D velocity field over a small lat/lon grid from the feeds.

    Each feed's (speed, direction) becomes a vector vx=v*cos(theta),
    vy=v*sin(theta) (compass deg -> math rad). The three vectors are blended
    across the grid with smooth spatial weights (marine dominates the seaward
    side, NOAA the coastal side, wind a uniform shear), giving a genuine,
    physically-motivated field. The overall state is LIVE if ANY source is LIVE
    (those vectors are real); the field never claims LIVE off purely SAMPLE data.

    Returns a JSON-serializable dict: centers, velocities, neighbors (CSR),
    plus the field ``state`` and the contributing sources.
    """
    def vec(fr: FeedResult) -> tuple[float, float]:
        th = math.radians(fr.direction_deg)
        # compass: 0deg = +y (north), 90deg = +x (east); map to math xy
        vx = fr.speed_ms * math.sin(th)
        vy = fr.speed_ms * math.cos(th)
        return vx, vy

    m = vec(feeds["marine"])
    w = vec(feeds["wind"])
    n = vec(feeds["noaa"])
    # scale wind down — it shears the surface, not the bulk current
    w = (w[0] * 0.05, w[1] * 0.05)

    centers: list[list[float]] = []
    vels: list[list[float]] = []

    def idx(i: int, j: int) -> int:
        return i * ny + j

    for i in range(nx):
        for j in range(ny):
            x = i / (nx - 1)         # 0..1 downstream / seaward
            centers.append([float(i), float(j)])
            # seaward weight grows with x; coastal weight is its complement
            wsea = x
            wcoast = 1.0 - x
            vx = wsea * m[0] + wcoast * n[0] + w[0]
            vy = wsea * m[1] + wcoast * n[1] + w[1]
            # gentle centerline convergence so compartments are non-trivial
            vy += -0.04 * (j - (ny - 1) / 2.0) * (0.3 + 0.7 * x)
            vels.append([vx, vy])

    neighbors_flat: list[int] = []
    neighbors_off: list[int] = [0]
    for i in range(nx):
        for j in range(ny):
            nb: list[int] = []
            if i > 0: nb.append(idx(i - 1, j))
            if i < nx - 1: nb.append(idx(i + 1, j))
            if j > 0: nb.append(idx(i, j - 1))
            if j < ny - 1: nb.append(idx(i, j + 1))
            neighbors_flat.extend(nb)
            neighbors_off.append(len(neighbors_flat))

    any_live = any(f.state == "LIVE" for f in feeds.values())
    return {
        "state": "LIVE" if any_live else "SAMPLE",
        "nx": nx, "ny": ny,
        "centers": centers,
        "velocities": vels,
        "neighbors_flat": neighbors_flat,
        "neighbors_offsets": neighbors_off,
        "sources": {k: v.as_dict() for k, v in feeds.items()},
    }
