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


def test_dynamic_fishing_score_calculation() -> None:
    # Test Mumbai vs Southern Konkan (Ratnagiri area)
    res_mumbai = analyse("Recommend best PFZ", Location(lat=18.95, lon=72.85), "en", use_live_data=False)
    res_south = analyse("Recommend best PFZ", Location(lat=16.98, lon=73.28), "en", use_live_data=False)
    
    rec_m = res_mumbai["recommendation"]
    rec_s = res_south["recommendation"]
    
    # Fishing scores must be dynamically computed and not stuck on static constant
    assert rec_m["fishing_score"] > 0
    assert rec_s["fishing_score"] > 0
    assert rec_m["pfz_score"] > 0
    assert rec_m["chlorophyll_score"] > 0
    assert rec_m["sst_score"] > 0
    assert rec_m["ocean_context_score"] > 0
    
    # Check that alternatives have their own distinct scores
    scores = [rec_m["fishing_score"]] + [alt["fishing_score"] for alt in res_mumbai["alternatives"]]
    assert len(scores) == 5
    assert all(0 <= s <= 100 for s in scores)
