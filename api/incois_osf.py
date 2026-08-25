"""Read-only adapter for publicly exposed INCOIS Ocean State Forecast WMS.

This adapter intentionally uses only the same public WMS endpoints used by
the official OSF map. It does not bypass login, require a key, or treat an
unavailable response as data. Callers must retain `issued_time`, `valid_time`
and `source_mode` with every result.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlencode
from urllib.request import urlopen


WMS_ROOT = "https://incois.gov.in/thredds/wms/osf"
WAVE_DATASET = "ww3/rsmc_combined_ww3_{date}.nc"
CURRENT_DATASET = "currents/CURRENTS_NIO_{date}.nc"


@dataclass(frozen=True)
class OsfLayer:
    parameter: str
    dataset: str
    layer: str
    unit: str


LAYERS = {
    "wind_speed": OsfLayer("wind_speed", "wave", "UWND:VWND-mag", "m/s"),
    "significant_wave_height": OsfLayer("significant_wave_height", "wave", "HS", "m"),
    "wave_period": OsfLayer("wave_period", "wave", "T02", "s"),
    "swell_height": OsfLayer("swell_height", "wave", "PHS01", "m"),
    "swell_period": OsfLayer("swell_period", "wave", "PTP01", "s"),
    "surface_current_speed": OsfLayer("surface_current_speed", "current", "CURRENT", "m/s"),
}


def get_feature_info_url(parameter: str, latitude: float, longitude: float, dataset_date: str, valid_time: datetime) -> str:
    """Create a transparent GetFeatureInfo URL for a single map grid point.

    WMS 1.1.1 uses longitude/latitude axis order in the bounding box. The
    0.02-degree box with a centred 101×101 pixel query is intentionally small
    and makes the target coordinate auditable in the final source URL.
    """
    if parameter not in LAYERS:
        raise ValueError(f"Unsupported OSF parameter: {parameter}")
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("Latitude/longitude outside WGS84 bounds")
    layer = LAYERS[parameter]
    dataset = WAVE_DATASET.format(date=dataset_date) if layer.dataset == "wave" else CURRENT_DATASET.format(date=dataset_date)
    bbox = f"{longitude - .01:.5f},{latitude - .01:.5f},{longitude + .01:.5f},{latitude + .01:.5f}"
    query = urlencode({"SERVICE": "WMS", "VERSION": "1.1.1", "REQUEST": "GetFeatureInfo", "LAYERS": layer.layer, "QUERY_LAYERS": layer.layer, "STYLES": "", "BBOX": bbox, "SRS": "EPSG:4326", "WIDTH": 101, "HEIGHT": 101, "X": 50, "Y": 50, "INFO_FORMAT": "text/plain", "TIME": valid_time.strftime("%Y-%m-%dT%H:%M:%SZ")})
    return f"{WMS_ROOT}/{dataset}?{query}"


def fetch_feature_info(url: str, timeout_seconds: int = 20) -> str:
    """Fetch an official WMS text response; errors deliberately propagate."""
    with urlopen(url, timeout=timeout_seconds) as response:  # nosec B310 - URL is assembled from allowlisted WMS root
        if response.status != 200:
            raise RuntimeError(f"INCOIS WMS returned HTTP {response.status}")
        return response.read().decode("utf-8", errors="replace")
