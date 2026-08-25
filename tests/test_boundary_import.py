from pathlib import Path

from api.boundary_import import read_restricted_zones_csv


def test_point_only_restrictions_cannot_become_route_blocks() -> None:
    path = Path("data/raw/boundaries/restricted_zones.csv")
    if not path.exists():
        return
    zones = read_restricted_zones_csv(path)
    assert len(zones) == 4
    assert {zone.enforcement for zone in zones} == {"CONTEXT_ONLY"}
