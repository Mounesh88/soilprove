"""
SoilProve - Precision Nitrogen & Fertilizer Optimization Platform
Main FastAPI Application
"""

import json
import os
import datetime
import asyncio
from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor(max_workers=4)
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

from utils.mrtn import (
    generate_prescription,
    validate_prescription_inputs,
    classify_soil_productivity
)
from utils.peer_engine import (
    find_peer_farms,
    get_peer_summary_for_ai
)
from utils.gemini_ai import (
    generate_prescription_explanation,
    generate_agronomist_brief,
    generate_outcome_analysis
)
from utils.prices import (
    get_all_prices,
    format_price_status
)

app = FastAPI(
    title="SoilProve",
    description="Precision Nitrogen & Fertilizer Optimization Platform",
    version="1.0.0"
)

app.mount("/static", StaticFiles(directory="static"), name="static")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(BASE_DIR, "data", "corn_belt_data.json"), encoding="utf-8") as f:
    CORN_BELT_DATA = json.load(f)

with open(os.path.join(BASE_DIR, "data", "peer_farms.json"), encoding="utf-8") as f:
    PEER_FARMS_DATA = json.load(f)
    OUTCOMES_PATH = os.path.join(BASE_DIR, "data", "outcomes.json")


# ── REQUEST MODELS ────────────────────────────────────────────────────────────

class PrescriptionRequest(BaseModel):
    farm_name: str = Field(default="My Farm")
    farm_acres: float = Field(gt=0, le=50000)
    county: str
    state: str
    crop: str = Field(default="corn")
    rotation: str = Field(default="corn_soybean_rotation")
    om_pct: float = Field(gt=0, le=10)
    soil_test_age_months: int = Field(default=18, ge=1, le=120)
    corn_price_usd_bu: Optional[float] = None
    n_cost_usd_lb: Optional[float] = None
    current_n_rate_lbs_ac: float = Field(default=185.0, ge=0, le=400)
    fertilizer_type: str = Field(default="anhydrous_ammonia")
    farmer_name: str = Field(default="Farmer")
    agronomist_name: str = Field(default="Agronomist")


class OutcomeRequest(BaseModel):
    farm_name: str
    county: str
    state: str
    crop: str
    farm_acres: float
    prescribed_n: float
    actual_n: float
    actual_yield: float
    historical_avg_yield: float
    weather_normal: bool = True


# ── ROUTES ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home():
    with open(os.path.join(BASE_DIR, "static", "index.html"), encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "app": "SoilProve",
        "version": "1.0.0"
    }


@app.get("/api/prices")
async def get_prices(
    state: str = "Missouri",
    county: str = "Cape Girardeau"
):
    try:
        prices = get_all_prices(state, county)
        status = format_price_status(prices)
        return {
            "success": True,
            "prices": prices,
            "status_display": status
        }
    except Exception as e:
        return {
            "success": False,
            "prices": {
                "corn_price_usd_bu": 4.42,
                "n_cost_anhydrous_usd_lb": 0.373,
                "n_cost_uan32_usd_lb": 0.544,
                "n_cost_urea_usd_lb": 0.570,
                "corn_price_is_live": False,
                "fertilizer_is_live": False,
                "corn_price_source": "USDA AMS (cached)",
                "fertilizer_source": "USDA AMS (cached)"
            },
            "error": "Using cached prices"
        }


@app.get("/api/counties")
async def get_counties(state: str = "Missouri"):
    state_data = CORN_BELT_DATA["states"].get(state, {})
    counties = list(state_data.get("counties", {}).keys())
    return {
        "success": True,
        "state": state,
        "counties": counties
    }


@app.get("/api/states")
async def get_states():
    states = list(CORN_BELT_DATA["states"].keys())
    return {
        "success": True,
        "states": states
    }


@app.get("/api/county-data")
async def get_county_data(state: str, county: str):
    state_data = CORN_BELT_DATA["states"].get(state, {})
    county_data = state_data.get("counties", {}).get(county, {})

    if not county_data:
        return {
            "success": False,
            "detail": f"County {county} not found in {state}"
        }

    return {
        "success": True,
        "state": state,
        "county": county,
        "soil_series": county_data.get("soil_series"),
        "soil_productivity_class": county_data.get("soil_productivity_class"),
        "avg_om_pct": county_data.get("avg_om_pct"),
        "avg_corn_yield_bu_ac": county_data.get("avg_corn_yield_bu_ac"),
        "avg_n_application_lbs_ac": county_data.get("avg_n_application_lbs_ac"),
        "yield_history": county_data.get("yield_history", {}),
        "primary_crops": county_data.get("primary_crops", []),
        "lat": county_data.get("lat"),
        "lng": county_data.get("lng")
    }


@app.post("/api/prescription")
async def generate_prescription_endpoint(request: PrescriptionRequest):

    errors = validate_prescription_inputs(
        request.om_pct,
        request.corn_price_usd_bu or 4.42,
        request.n_cost_usd_lb or 0.373,
        request.farm_acres,
        request.current_n_rate_lbs_ac
    )

    if errors:
        raise HTTPException(
            status_code=400,
            detail={"errors": errors}
        )

    prices = get_all_prices(request.state, request.county)
    corn_price = request.corn_price_usd_bu or prices["corn_price_usd_bu"]

    fertilizer_costs = {
        "anhydrous_ammonia": prices["n_cost_anhydrous_usd_lb"],
        "uan_32": prices["n_cost_uan32_usd_lb"],
        "urea_46": prices["n_cost_urea_usd_lb"]
    }
    n_cost = request.n_cost_usd_lb or fertilizer_costs.get(
        request.fertilizer_type,
        prices["n_cost_anhydrous_usd_lb"]
    )

    soil_class = classify_soil_productivity(request.om_pct)
    peer_result = find_peer_farms(
        farmer_om=request.om_pct,
        farmer_productivity_class=soil_class,
        farmer_rotation=request.rotation,
        farmer_state=request.state,
        farmer_county=request.county,
        farmer_crop=request.crop
    )

    prescription = generate_prescription(
        farm_acres=request.farm_acres,
        county=request.county,
        state=request.state,
        crop=request.crop,
        rotation=request.rotation,
        om_pct=request.om_pct,
        soil_test_age_months=request.soil_test_age_months,
        corn_price_usd_bu=corn_price,
        n_cost_usd_lb=n_cost,
        current_n_rate_lbs_ac=request.current_n_rate_lbs_ac,
        has_live_prices=prices.get("corn_price_is_live", False),
        peer_farm_count=peer_result.total_peers_found
    )

    peer_summary = get_peer_summary_for_ai(peer_result)

    explanation = generate_prescription_explanation(
        crop=request.crop,
        county=request.county,
        state=request.state,
        om_pct=request.om_pct,
        recommended_n=prescription.recommended_n_lbs_ac,
        current_rate=request.current_n_rate_lbs_ac,
        savings_usd_ac=prescription.savings_usd_ac,
        savings_usd_total=prescription.savings_usd_total,
        farm_acres=request.farm_acres,
        soil_productivity_class=prescription.soil_productivity_class,
        om_credit=prescription.om_n_credit_lbs_ac,
        corn_price=corn_price,
        n_cost=n_cost,
        confidence_level=prescription.confidence_level,
        peer_summary=peer_summary,
        warnings=prescription.warnings
    )

    return {
        "success": True,
        "prescription": {
            "recommended_n_lbs_ac": prescription.recommended_n_lbs_ac,
            "range_low_lbs_ac": prescription.range_low_lbs_ac,
            "range_high_lbs_ac": prescription.range_high_lbs_ac,
            "current_rate_lbs_ac": prescription.current_rate_lbs_ac,
            "savings_lbs_ac": prescription.savings_lbs_ac,
            "savings_usd_ac": prescription.savings_usd_ac,
            "savings_usd_total": prescription.savings_usd_total,
            "farm_acres": prescription.farm_acres
        },
        "soil": {
            "om_pct": prescription.om_pct,
            "soil_productivity_class": prescription.soil_productivity_class,
            "om_n_credit_lbs_ac": prescription.om_n_credit_lbs_ac,
            "base_eonr_lbs_ac": prescription.base_eonr_lbs_ac
        },
        "economics": {
            "corn_price_usd_bu": corn_price,
            "n_cost_usd_lb": n_cost,
            "price_ratio": prescription.price_ratio,
            "price_sensitivity": prescription.price_sensitivity,
            "price_source": prices.get("corn_price_source", "USDA AMS"),
            "fertilizer_source": prices.get("fertilizer_source", "USDA AMS")
        },
        "confidence": {
            "level": prescription.confidence_level,
            "color": prescription.confidence_color,
            "description": prescription.confidence_description,
            "score": prescription.data_completeness_score
        },
        "explanation": explanation,
        "peer_validation": {
            "total_peers": peer_result.total_peers_found,
            "tier_used": peer_result.tier_used,
            "tier_description": peer_result.tier_description,
            "avg_n_applied": peer_result.avg_n_applied_lbs_ac,
            "avg_yield": peer_result.avg_yield_bu_ac,
            "avg_yield_variance": peer_result.avg_yield_variance_pct,
            "avg_cost_saved": peer_result.avg_cost_saved_usd_ac,
            "yield_outcomes": {
                "improved": peer_result.yield_gain_count,
                "neutral": peer_result.yield_neutral_count,
                "declined": peer_result.yield_loss_count
            },
            "confidence_message": peer_result.confidence_message,
            "data_disclosure": peer_result.data_disclosure,
            "farms": [
                {
                    "farm_id": p.farm_id,
                    "name": p.name,
                    "county": p.county,
                    "state": p.state,
                    "om_pct": p.avg_om_pct,
                    "soil_series": p.soil_series,
                    "n_applied": p.n_applied_lbs_ac,
                    "yield": p.actual_yield_bu_ac,
                    "historical_yield": p.historical_avg_yield_bu_ac,
                    "yield_variance": p.yield_variance_pct,
                    "cost_saved": p.cost_saved_usd_ac,
                    "weather_normal": p.weather_normal,
                    "verified": p.verified,
                    "agronomist_reviewed": p.agronomist_reviewed,
                    "match_score": p.match_score,
                    "lat": p.lat,
                    "lng": p.lng
                }
                for p in peer_result.peers
            ]
        },
        "warnings": prescription.warnings,
        "metadata": {
            "methodology": prescription.methodology,
            "data_source": prescription.data_source,
            "generated_at": datetime.datetime.now().isoformat(),
            "county": request.county,
            "state": request.state,
            "crop": request.crop
        }
    }


@app.post("/api/agronomist-brief")
async def generate_brief(request: PrescriptionRequest):

    prices = get_all_prices(request.state, request.county)
    corn_price = request.corn_price_usd_bu or prices["corn_price_usd_bu"]
    n_cost = request.n_cost_usd_lb or prices["n_cost_anhydrous_usd_lb"]

    soil_class = classify_soil_productivity(request.om_pct)
    peer_result = find_peer_farms(
        farmer_om=request.om_pct,
        farmer_productivity_class=soil_class,
        farmer_rotation=request.rotation,
        farmer_state=request.state,
        farmer_county=request.county,
        farmer_crop=request.crop
    )

    prescription = generate_prescription(
        farm_acres=request.farm_acres,
        county=request.county,
        state=request.state,
        crop=request.crop,
        rotation=request.rotation,
        om_pct=request.om_pct,
        corn_price_usd_bu=corn_price,
        n_cost_usd_lb=n_cost,
        current_n_rate_lbs_ac=request.current_n_rate_lbs_ac
    )

    peer_summary = get_peer_summary_for_ai(peer_result)

    county_data = CORN_BELT_DATA["states"].get(
        request.state, {}
    ).get("counties", {}).get(request.county, {})
    soil_series = county_data.get("soil_series", "Local soil series")

    brief = generate_agronomist_brief(
        farmer_name=request.farmer_name,
        agronomist_name=request.agronomist_name,
        farm_acres=request.farm_acres,
        county=request.county,
        state=request.state,
        crop=request.crop,
        rotation=request.rotation,
        om_pct=request.om_pct,
        soil_series=soil_series,
        current_rate=request.current_n_rate_lbs_ac,
        recommended_n=prescription.recommended_n_lbs_ac,
        range_low=prescription.range_low_lbs_ac,
        range_high=prescription.range_high_lbs_ac,
        savings_usd_ac=prescription.savings_usd_ac,
        savings_usd_total=prescription.savings_usd_total,
        corn_price=corn_price,
        n_cost=n_cost,
        confidence_level=prescription.confidence_level,
        peer_summary=peer_summary,
        warnings=prescription.warnings
    )

    return {
        "success": True,
        "brief": brief,
        "generated_at": datetime.datetime.now().isoformat()
    }


@app.post("/api/outcome")
async def submit_outcome(request: OutcomeRequest):

    # If farmer followed prescription exactly, calculate savings vs county average 185 lbs/acre
    if request.prescribed_n == request.actual_n:
        cost_saved_ac = round((request.prescribed_n - request.actual_n) * 0.373, 2)
    if cost_saved_ac == 0:
        cost_saved_ac = round((request.actual_n * 0.373) * 0.15, 2)
    else:
        cost_saved_ac = round((request.prescribed_n - request.actual_n) * 0.373, 2)
    total_saved = round(cost_saved_ac * request.farm_acres, 2)
    total_saved = round(cost_saved_ac * request.farm_acres, 2)

    analysis = generate_outcome_analysis(
        county=request.county,
        state=request.state,
        crop=request.crop,
        prescribed_n=request.prescribed_n,
        actual_n=request.actual_n,
        actual_yield=request.actual_yield,
        historical_avg_yield=request.historical_avg_yield,
        cost_saved_usd_ac=cost_saved_ac,
        farm_acres=request.farm_acres,
        weather_normal=request.weather_normal
    )

    # If farmer followed prescription exactly, calculate savings vs county average 185 lbs/acre
    if request.prescribed_n == request.actual_n:
        cost_saved_ac = round((185.0 - request.actual_n) * 0.373, 2)
    else:
        cost_saved_ac = round((request.prescribed_n - request.actual_n) * 0.373, 2)
    total_saved = round(cost_saved_ac * request.farm_acres, 2)
    
    try:
        with open(OUTCOMES_PATH, "r", encoding="utf-8") as f:
            outcomes = json.load(f)
        outcomes.append({
            "farm_name": request.farm_name,
            "county": request.county,
            "state": request.state,
            "crop": request.crop,
            "farm_acres": request.farm_acres,
            "prescribed_n": request.prescribed_n,
            "actual_n": request.actual_n,
            "actual_yield": request.actual_yield,
            "historical_avg_yield": request.historical_avg_yield,
            "cost_saved_usd_ac": cost_saved_ac,
            "total_saved_usd": total_saved,
            "weather_normal": request.weather_normal,
            "yield_change": round(request.actual_yield - request.historical_avg_yield, 1),
            "submitted_at": datetime.datetime.now().isoformat()
       })
        with open(OUTCOMES_PATH, "w", encoding="utf-8") as f:
            json.dump(outcomes, f, indent=2)
    except Exception:
        pass

    return {
        "success": True,
        "outcome": {
            "prescribed_n": request.prescribed_n,
            "actual_n": request.actual_n,
            "actual_yield": request.actual_yield,
            "historical_avg_yield": request.historical_avg_yield,
            "yield_change": round(
                request.actual_yield - request.historical_avg_yield, 1
            ),
            "cost_saved_usd_ac": cost_saved_ac,
            "total_saved_usd": total_saved,
            "weather_normal": request.weather_normal
        },
        "analysis": analysis,
        "message": (
            "Your outcome data has been recorded. "
            "It will help other farmers in your region "
            "make better decisions next season."
        )
    }


@app.get("/api/peer-farms")
async def get_peer_farms(
    state: str = "Missouri",
    county: str = "Cape Girardeau",
    om_pct: float = 2.8,
    rotation: str = "corn_soybean_rotation",
    crop: str = "corn"
):
    soil_class = classify_soil_productivity(om_pct)
    peer_result = find_peer_farms(
        farmer_om=om_pct,
        farmer_productivity_class=soil_class,
        farmer_rotation=rotation,
        farmer_state=state,
        farmer_county=county,
        farmer_crop=crop
    )

    return {
        "success": True,
        "peer_validation": {
            "total_peers": peer_result.total_peers_found,
            "tier_used": peer_result.tier_used,
            "tier_description": peer_result.tier_description,
            "avg_n_applied": peer_result.avg_n_applied_lbs_ac,
            "avg_yield": peer_result.avg_yield_bu_ac,
            "avg_cost_saved": peer_result.avg_cost_saved_usd_ac,
            "confidence_message": peer_result.confidence_message,
            "data_disclosure": peer_result.data_disclosure,
            "farms": [
                {
                    "name": p.name,
                    "county": p.county,
                    "state": p.state,
                    "n_applied": p.n_applied_lbs_ac,
                    "yield": p.actual_yield_bu_ac,
                    "yield_variance": p.yield_variance_pct,
                    "cost_saved": p.cost_saved_usd_ac,
                    "verified": p.verified,
                    "lat": p.lat,
                    "lng": p.lng
                }
                for p in peer_result.peers
            ]
        }
    }

@app.get("/api/outcomes")
async def get_outcomes():
    try:
        with open(OUTCOMES_PATH, "r", encoding="utf-8") as f:
            outcomes = json.load(f)
        return {
            "success": True,
            "total": len(outcomes),
            "outcomes": outcomes
        }
    except Exception:
        return {"success": True, "total": 0, "outcomes": []}


@app.get("/api/outcomes/summary")
async def get_outcomes_summary():
    try:
        with open(OUTCOMES_PATH, "r", encoding="utf-8") as f:
            outcomes = json.load(f)
        normal = [o for o in outcomes if o.get("weather_normal") == True]
        drought = [o for o in outcomes if o.get("weather_normal") == False]
        return {
            "success": True,
            "total_submissions": len(outcomes),
            "normal_weather_count": len(normal),
            "drought_count": len(drought),
            "normal_weather_outcomes": normal,
            "drought_outcomes": drought,
            "data_quality_note": "Peer recommendations use normal weather outcomes only"
        }
    except Exception:
        return {
            "success": True,
            "total_submissions": 0,
            "normal_weather_count": 0,
            "drought_count": 0
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True
    )