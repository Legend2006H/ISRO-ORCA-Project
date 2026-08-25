from datetime import UTC, datetime

from api.incois_osf import get_feature_info_url


def test_osf_url_is_allowlisted_and_auditable() -> None:
    url = get_feature_info_url("significant_wave_height", 18.95, 72.85, "20260824", datetime(2026, 8, 25, 12, tzinfo=UTC))
    assert url.startswith("https://incois.gov.in/thredds/wms/osf/ww3/")
    assert "LAYERS=HS" in url
    assert "BBOX=72.84000%2C18.94000%2C72.86000%2C18.96000" in url
