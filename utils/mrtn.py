"""
MRTN (Maximum Return to Nitrogen) Calculation Engine
Source: University of Illinois and Iowa State University Extension
Citation: Sawyer J., Nafziger E., Randall G., Bundy L., Rehm G., Joern B. (2006)
"""

import json
import os
from dataclasses import dataclass
from typing import Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MRTN_PATH = os.path.join(BASE_DIR, "data", "mrtn_tables.json")

with open(MRTN_PATH, "r", encoding="utf-8") as f:
    MRTN_TABLES = json.load(f)


@dataclass
class PrescriptionResult:
    recommended_n_lbs_ac: float
    range_low_lbs_ac: float
    range_high_lbs_ac: float
    crop: str
    rotation: str
    soil_productivity_class: str
    om_pct: float
    corn_price_usd_bu: float
    n_cost_usd_lb: float
    price_ratio: float
    om_n_credit_lbs_ac: float
    base_eonr_lbs_ac: float
    current_rate_lbs_ac: float
    savings_lbs_ac: float
    savings_usd_ac: float
    savings_usd_total: float
    farm_acres: float
    confidence_level: str
    confidence_color: str
    confidence_description: str
    data_completeness_score: float
    methodology: str
    data_source: str
    warnings: list
    price_sensitivity: dict


def classify_soil_productivity(om_pct: float) -> str:
    if om_pct >= 3.5:
        return "high"
    elif om_pct >= 2.5:
        return "medium_high"
    elif om_pct >= 1.5:
        return "medium"
    else:
        return "low"


def calculate_om_n_credit(om_pct: float) -> float:
    om_tables = MRTN_TABLES["om_n_credit"]
    base_om = om_tables["base_om_pct"]
    credit_per_unit = om_tables["credit_per_om_unit"]
    min_credit = om_tables["min_credit_lbs_ac"]
    max_credit = om_tables["max_credit_lbs_ac"]
    credit = (om_pct - base_om) * credit_per_unit
    credit = max(min_credit, min(max_credit, credit))
    return round(credit, 1)


def calculate_price_ratio(n_cost_usd_lb: float, corn_price_usd_bu: float) -> float:
    if corn_price_usd_bu <= 0:
        return 0.15
    ratio = n_cost_usd_lb / corn_price_usd_bu
    return round(ratio, 3)


def get_mrtn_rate(
    crop: str,
    rotation: str,
    soil_productivity_class: str,
    price_ratio: float
) -> dict:
    crop_data = MRTN_TABLES.get(crop, {})
    if not crop_data:
        crop_data = MRTN_TABLES["corn"]

    rotation_data = crop_data.get(rotation, {})
    if not rotation_data:
        rotation_data = list(crop_data.values())[0]

    productivity_data = rotation_data.get(
        "productivity_classes", {}
    ).get(soil_productivity_class, {})

    if not productivity_data:
        productivity_data = rotation_data.get(
            "productivity_classes", {}
        ).get("medium", {})

    if "recommended_n_lbs_ac" in productivity_data:
        return {
            "eonr": productivity_data["recommended_n_lbs_ac"],
            "range_low": productivity_data["range_low"],
            "range_high": productivity_data["range_high"]
        }

    mrtn_by_ratio = productivity_data.get("mrtn_by_price_ratio", {})

    if not mrtn_by_ratio:
        return {"eonr": 170, "range_low": 150, "range_high": 190}

    available_ratios = [float(r) for r in mrtn_by_ratio.keys()]
    closest_ratio = min(available_ratios, key=lambda x: abs(x - price_ratio))
    closest_ratio_str = str(closest_ratio)

    for key in mrtn_by_ratio:
        if abs(float(key) - closest_ratio) < 0.001:
            closest_ratio_str = key
            break

    rate_data = mrtn_by_ratio[closest_ratio_str]
    return {
        "eonr": rate_data["eonr"],
        "range_low": rate_data["range_low"],
        "range_high": rate_data["range_high"]
    }


def calculate_confidence(
    om_pct: float,
    soil_test_age_months: int,
    peer_farm_count: int,
    has_live_prices: bool
) -> dict:
    score = 1.0
    warnings = []

    if soil_test_age_months > 36:
        score -= 0.3
        warnings.append(
            f"Soil test is {soil_test_age_months} months old. "
            f"Results most accurate with tests under 36 months."
        )
    elif soil_test_age_months > 24:
        score -= 0.15
        warnings.append(
            f"Soil test is {soil_test_age_months} months old. "
            f"Consider updating for maximum accuracy."
        )

    if peer_farm_count < 3:
        score -= 0.2
        warnings.append(
            f"Only {peer_farm_count} peer farms found in your area. "
            f"Recommendation based primarily on MRTN methodology."
        )

    if not has_live_prices:
        score -= 0.1
        warnings.append(
            "Using cached prices. Update corn and nitrogen prices "
            "for most accurate economic recommendation."
        )

    thresholds = MRTN_TABLES["confidence_thresholds"]

    if score >= thresholds["high"]["min_data_completeness"]:
        level = "HIGH"
        color = thresholds["high"]["color"]
        description = thresholds["high"]["description"]
    elif score >= thresholds["moderate"]["min_data_completeness"]:
        level = "MODERATE"
        color = thresholds["moderate"]["color"]
        description = thresholds["moderate"]["description"]
    else:
        level = "LOW"
        color = thresholds["low"]["color"]
        description = thresholds["low"]["description"]

    return {
        "level": level,
        "color": color,
        "description": description,
        "score": round(score, 2),
        "warnings": warnings
    }


def calculate_price_sensitivity(
    crop: str,
    rotation: str,
    soil_productivity_class: str,
    base_n_cost: float
) -> dict:
    scenarios = {}
    corn_prices = [3.50, 4.00, 4.50, 5.00, 5.50, 6.00]
    for price in corn_prices:
        ratio = calculate_price_ratio(base_n_cost, price)
        rate_data = get_mrtn_rate(crop, rotation, soil_productivity_class, ratio)
        scenarios[str(price)] = {
            "corn_price": price,
            "recommended_n": rate_data["eonr"],
            "price_ratio": round(ratio, 3)
        }
    return scenarios


def _make_non_mrtn_result(
    crop: str,
    rotation: str,
    om_pct: float,
    corn_price_usd_bu: float,
    n_cost_usd_lb: float,
    current_n_rate_lbs_ac: float,
    farm_acres: float,
    recommended_n: float,
    range_low: float,
    range_high: float,
    confidence_level: str,
    confidence_color: str,
    confidence_description: str,
    methodology: str,
    data_source: str,
    warnings: list
) -> PrescriptionResult:
    savings_lbs = round(current_n_rate_lbs_ac - recommended_n, 1)
    savings_usd_ac = round(savings_lbs * n_cost_usd_lb, 2)
    savings_total = round(savings_usd_ac * farm_acres, 2)
    return PrescriptionResult(
        recommended_n_lbs_ac=recommended_n,
        range_low_lbs_ac=range_low,
        range_high_lbs_ac=range_high,
        crop=crop,
        rotation=rotation,
        soil_productivity_class="medium",
        om_pct=om_pct,
        corn_price_usd_bu=corn_price_usd_bu,
        n_cost_usd_lb=n_cost_usd_lb,
        price_ratio=0.0,
        om_n_credit_lbs_ac=0.0,
        base_eonr_lbs_ac=recommended_n,
        current_rate_lbs_ac=current_n_rate_lbs_ac,
        savings_lbs_ac=savings_lbs,
        savings_usd_ac=savings_usd_ac,
        savings_usd_total=savings_total,
        farm_acres=farm_acres,
        confidence_level=confidence_level,
        confidence_color=confidence_color,
        confidence_description=confidence_description,
        data_completeness_score=0.75,
        methodology=methodology,
        data_source=data_source,
        warnings=warnings,
        price_sensitivity={}
    )


def generate_prescription(
    farm_acres: float,
    county: str,
    state: str,
    crop: str,
    rotation: str,
    om_pct: float,
    soil_test_age_months: int = 18,
    corn_price_usd_bu: float = 4.42,
    n_cost_usd_lb: float = 0.63,
    current_n_rate_lbs_ac: float = 185.0,
    has_live_prices: bool = True,
    peer_farm_count: int = 3
) -> PrescriptionResult:

    warnings = []

    # ── NON-MRTN CROPS ────────────────────────────────────────────────────────

    if crop == "soybeans":
        warnings.append(
            "Soybeans fix atmospheric nitrogen. "
            "Starter N only (0-30 lbs/acre recommended). "
            "MRTN methodology does not apply to soybeans."
        )
        return _make_non_mrtn_result(
            crop=crop, rotation=rotation, om_pct=om_pct,
            corn_price_usd_bu=corn_price_usd_bu,
            n_cost_usd_lb=n_cost_usd_lb,
            current_n_rate_lbs_ac=current_n_rate_lbs_ac,
            farm_acres=farm_acres,
            recommended_n=20.0, range_low=0.0, range_high=30.0,
            confidence_level="HIGH",
            confidence_color="#22c55e",
            confidence_description="Soybeans fix nitrogen — starter N only",
            methodology="University of Missouri Extension — Soybean N Management",
            data_source="Soybean N fixation research — starter N recommendation",
            warnings=warnings
        )

    if crop == "cotton":
        warnings.append(
            "Cotton N rates: 60-110 lbs/acre. "
            "University of Missouri Extension guidelines applied."
        )
        return _make_non_mrtn_result(
            crop=crop, rotation=rotation, om_pct=om_pct,
            corn_price_usd_bu=corn_price_usd_bu,
            n_cost_usd_lb=n_cost_usd_lb,
            current_n_rate_lbs_ac=current_n_rate_lbs_ac,
            farm_acres=farm_acres,
            recommended_n=80.0, range_low=60.0, range_high=110.0,
            confidence_level="MODERATE",
            confidence_color="#f59e0b",
            confidence_description="Cotton N — verify with local extension",
            methodology="University of Missouri Extension — Cotton N Management",
            data_source="Missouri Cotton Production Guide",
            warnings=warnings
        )

    if crop == "rice":
        warnings.append(
            "Rice N rates: 100-160 lbs/acre split application. "
            "Flood management critical. Apply pre-flood and mid-season."
        )
        return _make_non_mrtn_result(
            crop=crop, rotation=rotation, om_pct=om_pct,
            corn_price_usd_bu=corn_price_usd_bu,
            n_cost_usd_lb=n_cost_usd_lb,
            current_n_rate_lbs_ac=current_n_rate_lbs_ac,
            farm_acres=farm_acres,
            recommended_n=130.0, range_low=100.0, range_high=160.0,
            confidence_level="MODERATE",
            confidence_color="#f59e0b",
            confidence_description="Rice N — verify with local extension",
            methodology="University of Missouri Extension — Rice N Management",
            data_source="Missouri Rice Production Guide",
            warnings=warnings
        )

    # ── MRTN CROPS (corn, wheat, sorghum) ─────────────────────────────────────

    if om_pct < 0.4 or om_pct > 8.0:
        warnings.append(
            f"Organic matter of {om_pct}% is outside normal range. "
            f"Please verify your soil test data."
        )
        om_pct = max(0.4, min(8.0, om_pct))

    if corn_price_usd_bu < 2.0 or corn_price_usd_bu > 9.0:
        warnings.append(
            f"Corn price of ${corn_price_usd_bu}/bu seems unusual. "
            f"Please verify current market price."
        )

    if n_cost_usd_lb < 0.20 or n_cost_usd_lb > 2.0:
        warnings.append(
            f"Nitrogen cost of ${n_cost_usd_lb}/lb seems unusual. "
            f"Please verify current fertilizer price."
        )

    # Step 1: Classify soil productivity
    soil_productivity_class = classify_soil_productivity(om_pct)

    # Step 2: Calculate price ratio
    price_ratio = calculate_price_ratio(n_cost_usd_lb, corn_price_usd_bu)

    # Step 3: Get base MRTN rate
    mrtn_data = get_mrtn_rate(crop, rotation, soil_productivity_class, price_ratio)
    base_eonr = mrtn_data["eonr"]

    # Step 4: Apply OM nitrogen credit
    om_credit = calculate_om_n_credit(om_pct)

    # Step 5: Calculate final recommendation
    recommended_n = round(base_eonr - om_credit, 1)
    recommended_n = max(50, min(300, recommended_n))

    range_low = round(mrtn_data["range_low"] - om_credit, 1)
    range_high = round(mrtn_data["range_high"] - om_credit, 1)

    # Step 6: Calculate savings
    savings_lbs_ac = round(current_n_rate_lbs_ac - recommended_n, 1)
    savings_usd_ac = round(savings_lbs_ac * n_cost_usd_lb, 2)
    savings_usd_total = round(savings_usd_ac * farm_acres, 2)

    if savings_lbs_ac < 0:
        warnings.append(
            f"Your current rate of {current_n_rate_lbs_ac} lbs/acre "
            f"may be below the economic optimum. "
            f"Consider increasing to protect yield."
        )

    # Step 7: Calculate confidence
    confidence = calculate_confidence(
        om_pct, soil_test_age_months,
        peer_farm_count, has_live_prices
    )
    warnings.extend(confidence["warnings"])

    # Step 8: Price sensitivity
    sensitivity = calculate_price_sensitivity(
        crop, rotation, soil_productivity_class, n_cost_usd_lb
    )

    return PrescriptionResult(
        recommended_n_lbs_ac=recommended_n,
        range_low_lbs_ac=max(0, range_low),
        range_high_lbs_ac=range_high,
        crop=crop,
        rotation=rotation,
        soil_productivity_class=soil_productivity_class,
        om_pct=om_pct,
        corn_price_usd_bu=corn_price_usd_bu,
        n_cost_usd_lb=n_cost_usd_lb,
        price_ratio=price_ratio,
        om_n_credit_lbs_ac=om_credit,
        base_eonr_lbs_ac=base_eonr,
        current_rate_lbs_ac=current_n_rate_lbs_ac,
        savings_lbs_ac=savings_lbs_ac,
        savings_usd_ac=savings_usd_ac,
        savings_usd_total=savings_usd_total,
        farm_acres=farm_acres,
        confidence_level=confidence["level"],
        confidence_color=confidence["color"],
        confidence_description=confidence["description"],
        data_completeness_score=confidence["score"],
        methodology="MRTN - University of Illinois & Iowa State Extension",
        data_source="Sawyer et al. 2006 - Multi-year Corn Belt N Response Trials",
        warnings=warnings,
        price_sensitivity=sensitivity
    )


def validate_prescription_inputs(
    om_pct: float,
    corn_price: float,
    n_cost: float,
    farm_acres: float,
    current_rate: float
) -> list:
    errors = []
    if not 0.1 <= om_pct <= 10.0:
        errors.append("Organic matter must be between 0.1% and 10.0%")
    if not 1.0 <= corn_price <= 12.0:
        errors.append("Corn price must be between $1.00 and $12.00 per bushel")
    if not 0.10 <= n_cost <= 3.0:
        errors.append("Nitrogen cost must be between $0.10 and $3.00 per pound")
    if not 10 <= farm_acres <= 50000:
        errors.append("Farm acres must be between 10 and 50,000")
    if not 0 <= current_rate <= 400:
        errors.append("Current nitrogen rate must be between 0 and 400 lbs/acre")
    return errors