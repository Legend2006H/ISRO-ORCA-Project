from .models import RankedZone, ZoneCandidate


def rank_zones(candidates: list[ZoneCandidate]) -> list[RankedZone]:
    """Apply a transparent, versioned demonstration policy.

    Values are decision-support scores, not official INCOIS/ISRO thresholds.
    Hard blocks are evaluated before ranking so an attractive fishing score can
    never override a boundary or a critical hazard.
    """
    ranked: list[RankedZone] = []
    for candidate in candidates:
        reasons: list[str] = []
        blocked = candidate.restricted_zone or candidate.critical_hazard
        if candidate.restricted_zone:
            reasons.append("inside restricted or sensitive area")
        if candidate.critical_hazard:
            reasons.append("critical hazard advisory")
        fishing = (.45 * candidate.pfz_score + .30 * candidate.chlorophyll_score
                   + .15 * candidate.sst_score + .10 * candidate.ocean_context_score)
        safety = (.40 * candidate.wave_safety + .25 * candidate.wind_safety
                  + .15 * candidate.swell_safety + .10 * candidate.current_safety
                  + .10 * candidate.hazard_clearance)
        overall = (.45 * fishing + .40 * safety
                   + .10 * candidate.accessibility_score
                   + .05 * candidate.data_quality_score)
        ranked.append(RankedZone(**candidate.model_dump(), fishing_score=round(fishing, 1),
                                 safety_score=round(safety, 1), overall_score=round(overall, 1),
                                 rank=0, decision_status="BLOCKED" if blocked else "SECONDARY",
                                 rejected_reason=reasons))
    ranked.sort(key=lambda zone: (0 if zone.decision_status == "BLOCKED" else 1, zone.overall_score), reverse=True)
    for rank, zone in enumerate(ranked, start=1):
        zone.rank = rank
        if zone.decision_status != "BLOCKED" and rank == 1:
            zone.decision_status = "RECOMMENDED"
    return ranked
