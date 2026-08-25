"""Validated reader for official-style Maharashtra PFZ XLS advisories.

The advisory represents candidate points described by a coastal reference,
bearing, offshore-distance band, depth band and final target coordinate. It
does not contain a safety forecast and must never be used as one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


_DMS = re.compile(r"^(\d{1,3})\s+(\d{1,2})\s+(\d{1,2})\s+([NSEW])$")
_RANGE = re.compile(r"^(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)$")
_VALIDITY = re.compile(r"FORECAST VALIDITY FROM\s+(\d{1,2}\s+\w+\s+\d{4})\s+TO\s+(\d{1,2}\s+\w+\s+\d{4})")


@dataclass(frozen=True)
class PfzCandidate:
    coastal_reference: str
    direction: str
    bearing_deg: float
    distance_from_km: float
    distance_to_km: float
    depth_from_m: float
    depth_to_m: float
    latitude: float
    longitude: float


def _dms_to_decimal(value: str) -> float:
    match = _DMS.match(str(value).strip())
    if not match:
        raise ValueError(f"Invalid DMS coordinate: {value!r}")
    degrees, minutes, seconds, hemisphere = match.groups()
    if int(minutes) >= 60 or int(seconds) >= 60:
        raise ValueError(f"Invalid DMS minute/second value: {value!r}")
    decimal = int(degrees) + int(minutes) / 60 + int(seconds) / 3600
    return -decimal if hemisphere in {"S", "W"} else decimal


def _parse_range(value: str, unit: str) -> tuple[float, float]:
    match = _RANGE.match(str(value).strip())
    if not match:
        raise ValueError(f"Invalid {unit} range: {value!r}")
    start, end = map(float, match.groups())
    if start > end:
        raise ValueError(f"Invalid {unit} range order: {value!r}")
    return start, end


def read_pfz_xls(path: str | Path) -> tuple[str, list[PfzCandidate]]:
    """Return advisory validity text and normalized candidates from one XLS file."""
    sheet = pd.read_excel(Path(path), sheet_name="Forecast Data", header=None)
    heading = str(sheet.iloc[0, 0])
    if not _VALIDITY.search(heading):
        raise ValueError("PFZ advisory validity period is missing or malformed")

    records = sheet[pd.to_numeric(sheet[2], errors="coerce").notna()]
    candidates: list[PfzCandidate] = []
    seen_coordinates: set[tuple[float, float]] = set()
    for _, row in records.iterrows():
        lat, lon = _dms_to_decimal(row[5]), _dms_to_decimal(row[6])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError(f"Coordinate outside WGS84 bounds: {lat}, {lon}")
        if (lat, lon) in seen_coordinates:
            raise ValueError(f"Duplicate PFZ coordinate: {lat}, {lon}")
        seen_coordinates.add((lat, lon))
        distance_from, distance_to = _parse_range(row[3], "distance")
        depth_from, depth_to = _parse_range(row[4], "depth")
        bearing = float(row[2])
        if not 0 <= bearing <= 360:
            raise ValueError(f"Bearing outside 0–360°: {bearing}")
        candidates.append(PfzCandidate(str(row[0]).strip(), str(row[1]).strip(), bearing,
                                       distance_from, distance_to, depth_from, depth_to, lat, lon))
    if not candidates:
        raise ValueError("No PFZ candidate rows were found")
    return heading, candidates
