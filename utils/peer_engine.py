"""
Peer Farm Matching Engine
Matches farmer's soil profile to similar farms in the database
Uses multi-tier fallback for sparse data conditions
"""

import json
import os
from dataclasses import dataclass
from typing import List, Optional

# Load peer farms data
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PEER_FARMS_PATH = os.path.join(BASE_DIR, "data", "peer_farms.json")
CORN_BELT_PATH = os.path.join(BASE_DIR, "data", "corn_belt_data.json")

with open(PEER_FARMS_PATH, "r") as f:
    PEER_FARMS_DATA = json.load(f)

with open(CORN_BELT_PATH, "r") as f:
    CORN_BELT_DATA = json.load(f)


@dataclass
class PeerFarm:
    """Single peer farm result"""
    farm_id: str
    name: str
    county: str
    state: str
    farm_size_acres: float
    soil_series: str
    soil_productivity_class: str
    avg_om_pct: float
    rotation: str
    
    # Season results
    year: int
    n_applied_lbs_ac: float
    flat_rate_prior_lbs_ac: float
    actual_yield_bu_ac: float
    historical_avg_yield_bu_ac: float
    yield_variance_pct: float
    cost_saved_usd_ac: float
    weather_normal: bool
    drought_stress: bool
    verified: bool
    agronomist_reviewed: bool
    
    # Match quality
    match_score: float
    match_tier: int
    match_reason: str
    
    # Location
    lat: float
    lng: float


@dataclass
class PeerValidationResult:
    """Complete peer validation output"""
    peers: List[PeerFarm]
    tier_used: int
    tier_description: str
    total_peers_found: int
    avg_n_applied_lbs_ac: float
    avg_yield_bu_ac: float
    avg_yield_variance_pct: float
    avg_cost_saved_usd_ac: float
    yield_loss_count: int
    yield_neutral_count: int
    yield_gain_count: int
    confidence_message: str
    data_disclosure: str


def calculate_om_similarity(om_a: float, om_b: float) -> float:
    """
    Calculate similarity score between two OM values
    Returns 0.0 to 1.0 (1.0 = identical)
    """
    diff = abs(om_a - om_b)
    if diff <= 0.3:
        return 1.0
    elif diff <= 0.6:
        return 0.8
    elif diff <= 1.0:
        return 0.6
    elif diff <= 1.5:
        return 0.4
    else:
        return 0.2


def calculate_match_score(
    farmer_om: float,
    farmer_productivity_class: str,
    farmer_rotation: str,
    farmer_state: str,
    farmer_county: str,
    peer: dict
) -> float:
    """
    Calculate overall match score between farmer and peer farm
    Returns 0.0 to 1.0
    """
    score = 0.0

    # OM similarity (40% weight)
    om_score = calculate_om_similarity(farmer_om, peer["avg_om_pct"])
    score += om_score * 0.40

    # Productivity class match (25% weight)
    if peer["soil_productivity_class"] == farmer_productivity_class:
        score += 0.25
    elif abs(
        ["low", "medium", "medium_high", "high"].index(
            peer["soil_productivity_class"]
        ) -
        ["low", "medium", "medium_high", "high"].index(
            farmer_productivity_class
        )
    ) == 1:
        score += 0.15

    # Rotation match (20% weight)
    if peer["rotation"] == farmer_rotation:
        score += 0.20
    else:
        score += 0.05

    # Geographic proximity (15% weight)
    if peer["county"] == farmer_county and peer["state"] == farmer_state:
        score += 0.15
    elif peer["state"] == farmer_state:
        score += 0.10
    elif peer["state_abbr"] in get_neighboring_states(farmer_state):
        score += 0.05

    return round(score, 3)


def get_neighboring_states(state: str) -> list:
    """
    Returns neighboring states for geographic proximity matching
    """
    neighbors = {
        "Missouri": ["IL", "IA", "KS", "KY", "TN", "AR", "OK", "NE"],
        "Iowa": ["MO", "IL", "MN", "NE", "SD", "WI"],
        "Illinois": ["MO", "IA", "IN", "KY", "WI"],
        "Indiana": ["IL", "OH", "KY", "MI"],
        "Kansas": ["MO", "NE", "CO", "OK"],
        "Nebraska": ["MO", "IA", "KS", "CO", "SD", "WY"],
        "Minnesota": ["IA", "WI", "ND", "SD"],
        "Ohio": ["IN", "KY", "WV", "PA", "MI"],
        "Kentucky": ["MO", "IL", "IN", "OH", "TN"],
        "Tennessee": ["MO", "KY", "AL", "GA", "NC", "VA", "AR"]
    }
    return neighbors.get(state, [])


def get_tier_description(tier: int) -> str:
    """Human readable tier description"""
    descriptions = {
        1: "Exact match — same county, similar soil, same rotation",
        2: "Strong match — same state, similar soil type",
        3: "Regional match — neighboring states, similar conditions",
        4: "Broad match — Corn Belt farms with similar productivity class"
    }
    return descriptions.get(tier, "Regional agricultural data")


def get_data_disclosure(tier: int, count: int) -> str:
    """
    Transparent disclosure about data quality
    Never hide data limitations from farmer
    """
    if tier == 1:
        return (
            f"Showing {count} farms in your county and surrounding area "
            f"with similar soil profiles. High relevance to your operation."
        )
    elif tier == 2:
        return (
            f"Showing {count} farms in your state with similar soil conditions. "
            f"Good relevance — same climate and market conditions."
        )
    elif tier == 3:
        return (
            f"Showing {count} farms from neighboring states with similar soils. "
            f"Moderate relevance — verify with local agronomist."
        )
    else:
        return (
            f"Limited local peer data available. Showing {count} Corn Belt farms "
            f"with similar productivity class. Use as directional guidance only. "
            f"Your data will help future farmers in your area."
        )


def find_peer_farms(
    farmer_om: float,
    farmer_productivity_class: str,
    farmer_rotation: str,
    farmer_state: str,
    farmer_county: str,
    farmer_crop: str,
    min_peers: int = 3,
    max_peers: int = 5
) -> PeerValidationResult:
    """
    Main peer matching function with 4-tier fallback
    Never returns empty results
    """

    all_farms = PEER_FARMS_DATA["peer_farms"]

    # Filter by crop first
    crop_farms = [
        f for f in all_farms
        if f["primary_crop"] == farmer_crop
   ]

    if not crop_farms:
        # For non-corn crops show farms with note
        crop_farms = all_farms
        # Add note that peer data is from similar soil farms not same crop

    matched_peers = []

    # ── TIER 1: Same county, same state ──────────────────────────
    tier1_farms = [
        f for f in crop_farms
        if f["county"] == farmer_county
        and f["state"] == farmer_state
    ]

    if len(tier1_farms) >= min_peers:
        for farm in tier1_farms:
            score = calculate_match_score(
                farmer_om, farmer_productivity_class,
                farmer_rotation, farmer_state,
                farmer_county, farm
            )
            matched_peers.append((farm, score, 1))
        tier_used = 1

    # ── TIER 2: Same state ───────────────────────────────────────
    if len(matched_peers) < min_peers:
        matched_peers = []
        tier2_farms = [
            f for f in crop_farms
            if f["state"] == farmer_state
        ]

        if len(tier2_farms) >= min_peers:
            for farm in tier2_farms:
                score = calculate_match_score(
                    farmer_om, farmer_productivity_class,
                    farmer_rotation, farmer_state,
                    farmer_county, farm
                )
                matched_peers.append((farm, score, 2))
            tier_used = 2

    # ── TIER 3: Neighboring states ───────────────────────────────
    if len(matched_peers) < min_peers:
        matched_peers = []
        neighboring = get_neighboring_states(farmer_state)
        tier3_farms = [
            f for f in crop_farms
            if f["state_abbr"] in neighboring
            or f["state"] == farmer_state
        ]

        if len(tier3_farms) >= min_peers:
            for farm in tier3_farms:
                score = calculate_match_score(
                    farmer_om, farmer_productivity_class,
                    farmer_rotation, farmer_state,
                    farmer_county, farm
                )
                matched_peers.append((farm, score, 3))
            tier_used = 3

    # ── TIER 4: All Corn Belt farms ──────────────────────────────
    if len(matched_peers) < min_peers:
        matched_peers = []
        for farm in crop_farms:
            score = calculate_match_score(
                farmer_om, farmer_productivity_class,
                farmer_rotation, farmer_state,
                farmer_county, farm
            )
            matched_peers.append((farm, score, 4))
        tier_used = 4

    # Sort by match score descending
    matched_peers.sort(key=lambda x: x[1], reverse=True)

    # Take top N peers
    top_peers = matched_peers[:max_peers]

    # Build PeerFarm objects
    peer_results = []
    for farm, score, tier in top_peers:
        # Get most recent season
        seasons = farm.get("seasons", [])
        if not seasons:
            continue

        latest_season = sorted(seasons, key=lambda s: s["year"])[-1]

        peer_results.append(PeerFarm(
            farm_id=farm["farm_id"],
            name=farm["name"],
            county=farm["county"],
            state=farm["state"],
            farm_size_acres=farm["farm_size_acres"],
            soil_series=farm["soil_series"],
            soil_productivity_class=farm["soil_productivity_class"],
            avg_om_pct=farm["avg_om_pct"],
            rotation=farm["rotation"],

            year=latest_season["year"],
            n_applied_lbs_ac=latest_season["n_applied_lbs_ac"],
            flat_rate_prior_lbs_ac=latest_season["flat_rate_prior_lbs_ac"],
            actual_yield_bu_ac=latest_season["actual_yield_bu_ac"],
            historical_avg_yield_bu_ac=latest_season[
                "historical_avg_yield_bu_ac"
            ],
            yield_variance_pct=latest_season["yield_variance_pct"],
            cost_saved_usd_ac=latest_season["cost_saved_usd_ac"],
            weather_normal=latest_season["weather_normal"],
            drought_stress=latest_season["drought_stress"],
            verified=latest_season["verified"],
            agronomist_reviewed=latest_season["agronomist_reviewed"],

            match_score=score,
            match_tier=tier,
            match_reason=get_tier_description(tier),

            lat=farm["lat"],
            lng=farm["lng"]
        ))

    # Calculate aggregate statistics
    if peer_results:
        avg_n = round(
            sum(p.n_applied_lbs_ac for p in peer_results) / len(peer_results),
            1
        )
        avg_yield = round(
            sum(p.actual_yield_bu_ac for p in peer_results) / len(peer_results),
            1
        )
        avg_variance = round(
            sum(p.yield_variance_pct for p in peer_results) / len(peer_results),
            1
        )
        avg_saved = round(
            sum(p.cost_saved_usd_ac for p in peer_results) / len(peer_results),
            2
        )
        yield_loss = sum(
            1 for p in peer_results if p.yield_variance_pct < -2.0
        )
        yield_neutral = sum(
            1 for p in peer_results
            if -2.0 <= p.yield_variance_pct <= 2.0
        )
        yield_gain = sum(
            1 for p in peer_results if p.yield_variance_pct > 2.0
        )
    else:
        avg_n = avg_yield = avg_variance = avg_saved = 0
        yield_loss = yield_neutral = yield_gain = 0
        tier_used = 4

    # Build confidence message
    if tier_used == 1:
        confidence_msg = (
            f"Strong peer validation — {len(peer_results)} farms "
            f"found in your county with similar soil conditions."
        )
    elif tier_used == 2:
        confidence_msg = (
            f"Good peer validation — {len(peer_results)} farms "
            f"found in your state with similar conditions."
        )
    elif tier_used == 3:
        confidence_msg = (
            f"Regional peer validation — {len(peer_results)} farms "
            f"from neighboring states with similar soil types."
        )
    else:
        confidence_msg = (
            f"Broad peer validation — {len(peer_results)} Corn Belt farms "
            f"with similar productivity class. Limited local data available."
        )

    return PeerValidationResult(
        peers=peer_results,
        tier_used=tier_used,
        tier_description=get_tier_description(tier_used),
        total_peers_found=len(peer_results),
        avg_n_applied_lbs_ac=avg_n,
        avg_yield_bu_ac=avg_yield,
        avg_yield_variance_pct=avg_variance,
        avg_cost_saved_usd_ac=avg_saved,
        yield_loss_count=yield_loss,
        yield_neutral_count=yield_neutral,
        yield_gain_count=yield_gain,
        confidence_message=confidence_msg,
        data_disclosure=get_data_disclosure(tier_used, len(peer_results))
    )


def get_peer_summary_for_ai(peer_result: PeerValidationResult) -> str:
    """
    Format peer data for Gemini AI explanation
    Returns clean text summary
    """
    if not peer_result.peers:
        return "No peer farm data available for this region."

    lines = []
    lines.append(
        f"PEER FARM VALIDATION DATA ({peer_result.total_peers_found} farms):"
    )
    lines.append(f"Match Quality: {peer_result.tier_description}")
    lines.append("")

    for i, peer in enumerate(peer_result.peers, 1):
        lines.append(f"Farm {i}: {peer.county} County, {peer.state}")
        lines.append(f"  Soil: {peer.soil_series} (OM: {peer.avg_om_pct}%)")
        lines.append(
            f"  Applied: {peer.n_applied_lbs_ac} lbs/acre "
            f"(was applying {peer.flat_rate_prior_lbs_ac} lbs/acre)"
        )
        lines.append(
            f"  Yield: {peer.actual_yield_bu_ac} bu/acre "
            f"(historical avg: {peer.historical_avg_yield_bu_ac} bu/acre)"
        )
        lines.append(
            f"  Yield change: {peer.yield_variance_pct:+.1f}% "
            f"vs historical average"
        )
        lines.append(
            f"  Cost saved: ${peer.cost_saved_usd_ac:.2f}/acre"
        )
        lines.append(
            f"  Weather: {'Normal' if peer.weather_normal else 'Abnormal'}"
        )
        lines.append(
            f"  Verified: {'Yes' if peer.verified else 'No'}"
        )
        lines.append("")

    lines.append(f"AGGREGATE RESULTS:")
    lines.append(
        f"  Average N applied: {peer_result.avg_n_applied_lbs_ac} lbs/acre"
    )
    lines.append(
        f"  Average yield: {peer_result.avg_yield_bu_ac} bu/acre"
    )
    lines.append(
        f"  Average yield variance: "
        f"{peer_result.avg_yield_variance_pct:+.1f}%"
    )
    lines.append(
        f"  Average cost saved: ${peer_result.avg_cost_saved_usd_ac:.2f}/acre"
    )
    lines.append(
        f"  Yield outcomes: "
        f"{peer_result.yield_gain_count} improved, "
        f"{peer_result.yield_neutral_count} neutral, "
        f"{peer_result.yield_loss_count} declined"
    )

    return "\n".join(lines)