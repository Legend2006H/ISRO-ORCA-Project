"""Safe boundary-input classifier.

Point-only inputs are useful for map context but are never silently converted
into legal exclusion polygons. A zone becomes route-blocking only when an
official source and explicit polygon or radius are supplied.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class BoundaryPoint:
    name: str
    restriction_type: str
    latitude: float
    longitude: float
    radius_km: float | None
    source_url: str | None
    enforcement: str
    note: str


def read_restricted_zones_csv(path: str | Path) -> list[BoundaryPoint]:
    data = pd.read_csv(path).fillna("")
    required = {"name", "restriction_type", "latitude", "longitude", "radius_km", "source_url", "notes"}
    missing = required - set(data.columns)
    if missing:
        raise ValueError(f"Missing boundary columns: {sorted(missing)}")
    results: list[BoundaryPoint] = []
    for _, row in data.iterrows():
        lat, lon = float(row.latitude), float(row.longitude)
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError(f"Invalid coordinate for {row.name}")
        radius = float(row.radius_km) if str(row.radius_km).strip() else None
        source = str(row.source_url).strip()
        official_source = source.startswith("https://") and "PASTE_" not in source
        enforcement = "BLOCK" if official_source and radius and radius > 0 else "CONTEXT_ONLY"
        results.append(BoundaryPoint(str(row["name"]), str(row.restriction_type), lat, lon, radius, source or None, enforcement, str(row.notes)))
    return results
