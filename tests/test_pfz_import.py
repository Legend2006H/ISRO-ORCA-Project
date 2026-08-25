from pathlib import Path

from api.pfz_import import read_pfz_xls


def test_supplied_maharashtra_pfz_advisory() -> None:
    repo_path = Path(__file__).resolve().parents[1] / "data" / "raw" / "pfz" / "PfzForecast_MAHARASHTRA.xls"
    downloads_path = Path(r"C:\Users\hrush\Downloads\PfzForecast_MAHARASHTRA.xls")
    path = repo_path if repo_path.exists() else downloads_path
    assert path.exists(), f"PFZ file not found at {path}"
    validity, candidates = read_pfz_xls(path)
    assert "25 Aug 2026 TO  26 Aug 2026" in validity
    assert len(candidates) == 89
    assert len({(candidate.latitude, candidate.longitude) for candidate in candidates}) == 89
