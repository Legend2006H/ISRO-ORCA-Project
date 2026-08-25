from api.models import Location
from api.offline_service import analyse


def test_cached_analysis_uses_supplied_pfz_and_ocean_files() -> None:
    result = analyse("Where is the nearest PFZ and is it safe?", Location(lat=18.95, lon=72.85), "en")

    assert result["source_mode"] == "CACHED"
    assert result["recommendation"]["name"].startswith("PFZ near ")
    assert len(result["alternatives"]) == 4
    assert result["safety"]["wave_height_m"] > 1.5
    assert result["safety"]["departure_allowed"] is False
    assert any(item["id"] == "pfz_advisory" for item in result["evidence"])
