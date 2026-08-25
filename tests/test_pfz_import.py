from pathlib import Path

from api.pfz_import import read_pfz_xls


def test_supplied_maharashtra_pfz_advisory() -> None:
    path = Path(r"C:\Users\hrush\Downloads\PfzForecast_MAHARASHTRA.xls")
    if not path.exists():
        return
    validity, candidates = read_pfz_xls(path)
    assert "25 Aug 2026 TO  26 Aug 2026" in validity
    assert len(candidates) == 89
    assert len({(candidate.latitude, candidate.longitude) for candidate in candidates}) == 89
