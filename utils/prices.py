"""
Real-Time Price Data Service
Fetches live corn and nitrogen prices from USDA AMS
Falls back to cached/static data if API unavailable
"""

import os
import json
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

USDA_NASS_KEY = os.getenv("USDA_NASS_KEY")
NOAA_KEY = os.getenv("NOAA_KEY")

# Static fallback prices (USDA AMS May 2026)
# Updated from: https://www.ams.usda.gov/market-news/fertilizer
FALLBACK_PRICES = {
    "corn_price_usd_bu": 4.42,
    "corn_price_source": "USDA AMS Corn Belt Elevator (cached)",
    "corn_price_date": "2026-05-19",
    
    "anhydrous_ammonia_usd_ton": 612,
    "uan_32_usd_ton": 348,
    "urea_46_usd_ton": 524,
    
    "n_cost_anhydrous_usd_lb": 0.373,
    "n_cost_uan32_usd_lb": 0.544,
    "n_cost_urea_usd_lb": 0.570,
    
    "fertilizer_source": "USDA AMS Fertilizer Report (cached)",
    "fertilizer_date": "2026-05-19",
    
    "is_live": False,
    "last_updated": "2026-05-19T00:00:00"
}

# Missouri elevator locations for price lookup
MISSOURI_ELEVATORS = {
    "Cape Girardeau": {"lat": 37.3059, "lng": -89.5181},
    "New Madrid": {"lat": 36.5867, "lng": -89.5275},
    "Sikeston": {"lat": 36.8762, "lng": -89.5784},
    "Kennett": {"lat": 36.2359, "lng": -90.0551},
    "Poplar Bluff": {"lat": 36.7570, "lng": -90.3929}
}

# Price cache - in memory for session
_price_cache = {}
_cache_timestamp = None
CACHE_DURATION_MINUTES = 60


def is_cache_valid() -> bool:
    """Check if cached prices are still fresh"""
    global _cache_timestamp
    if not _cache_timestamp or not _price_cache:
        return False
    age = datetime.now() - _cache_timestamp
    return age < timedelta(minutes=CACHE_DURATION_MINUTES)


def fetch_corn_price_usda(state: str = "Missouri") -> dict:
    """
    Fetch live corn cash price from USDA NASS
    Returns price dict with source and timestamp
    """
    if not USDA_NASS_KEY or USDA_NASS_KEY == "optional_for_now":
        return {
            "price": FALLBACK_PRICES["corn_price_usd_bu"],
            "source": FALLBACK_PRICES["corn_price_source"],
            "date": FALLBACK_PRICES["corn_price_date"],
            "is_live": False
        }

    try:
        # USDA NASS Quick Stats API
        url = "https://quickstats.nass.usda.gov/api/api_GET/"
        params = {
            "key": USDA_NASS_KEY,
            "commodity_desc": "CORN",
            "statisticcat_desc": "PRICE RECEIVED",
            "unit_desc": "$ / BU",
            "state_name": state.upper(),
            "year": str(datetime.now().year),
            "format": "json"
        }

        response = requests.get(
            station_url,
            headers=headers,
            params=station_params,
            timeout=5
   )

        if response.status_code == 200:
            data = response.json()
            items = data.get("data", [])

            if items:
                # Get most recent price
                latest = sorted(
                    items,
                    key=lambda x: x.get("end_code", "0"),
                    reverse=True
                )[0]

                price = float(latest.get("Value", "0").replace(",", ""))
                if price > 0:
                    return {
                        "price": price,
                        "source": f"USDA NASS Live — {state}",
                        "date": datetime.now().strftime("%Y-%m-%d"),
                        "is_live": True
                    }

    except Exception:
        pass

    # Fallback
    return {
        "price": FALLBACK_PRICES["corn_price_usd_bu"],
        "source": FALLBACK_PRICES["corn_price_source"],
        "date": FALLBACK_PRICES["corn_price_date"],
        "is_live": False
    }


def fetch_fertilizer_prices_usda() -> dict:
    """
    Fetch live fertilizer prices from USDA AMS
    Returns dict with prices for major N fertilizer types
    """
    if not USDA_NASS_KEY or USDA_NASS_KEY == "optional_for_now":
        return {
            "anhydrous_ammonia_usd_ton": FALLBACK_PRICES[
                "anhydrous_ammonia_usd_ton"
            ],
            "uan_32_usd_ton": FALLBACK_PRICES["uan_32_usd_ton"],
            "urea_46_usd_ton": FALLBACK_PRICES["urea_46_usd_ton"],
            "n_cost_anhydrous_usd_lb": FALLBACK_PRICES[
                "n_cost_anhydrous_usd_lb"
            ],
            "n_cost_uan32_usd_lb": FALLBACK_PRICES["n_cost_uan32_usd_lb"],
            "n_cost_urea_usd_lb": FALLBACK_PRICES["n_cost_urea_usd_lb"],
            "source": FALLBACK_PRICES["fertilizer_source"],
            "date": FALLBACK_PRICES["fertilizer_date"],
            "is_live": False
        }

    try:
        # USDA AMS Fertilizer API
        url = (
            "https://marsapi.ams.usda.gov/services/v1.2/reports/"
            "2572?allSections=true"
        )
        headers = {"Accept": "application/json"}

        response = requests.get(url, headers=headers, timeout=5)

        if response.status_code == 200:
            data = response.json()
            results = data.get("results", [])

            prices = {}
            for item in results:
                commodity = item.get("commodity", "").lower()
                price_str = item.get("price", "0")

                try:
                    price = float(
                        str(price_str).replace(",", "").replace("$", "")
                    )
                except ValueError:
                    continue

                if "anhydrous" in commodity and price > 0:
                    prices["anhydrous"] = price
                elif "uan" in commodity and "32" in commodity and price > 0:
                    prices["uan32"] = price
                elif "urea" in commodity and price > 0:
                    prices["urea"] = price

            if prices:
                anhydrous = prices.get(
                    "anhydrous",
                    FALLBACK_PRICES["anhydrous_ammonia_usd_ton"]
                )
                uan32 = prices.get(
                    "uan32",
                    FALLBACK_PRICES["uan_32_usd_ton"]
                )
                urea = prices.get(
                    "urea",
                    FALLBACK_PRICES["urea_46_usd_ton"]
                )

                return {
                    "anhydrous_ammonia_usd_ton": anhydrous,
                    "uan_32_usd_ton": uan32,
                    "urea_46_usd_ton": urea,
                    "n_cost_anhydrous_usd_lb": round(anhydrous / (2000 * 0.82), 3),
                    "n_cost_uan32_usd_lb": round(uan32 / (2000 * 0.32), 3),
                    "n_cost_urea_usd_lb": round(urea / (2000 * 0.46), 3),
                    "source": "USDA AMS Live Fertilizer Report",
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "is_live": True
                }

    except Exception:
        pass

    # Fallback
    return {
        "anhydrous_ammonia_usd_ton": FALLBACK_PRICES[
            "anhydrous_ammonia_usd_ton"
        ],
        "uan_32_usd_ton": FALLBACK_PRICES["uan_32_usd_ton"],
        "urea_46_usd_ton": FALLBACK_PRICES["urea_46_usd_ton"],
        "n_cost_anhydrous_usd_lb": FALLBACK_PRICES[
            "n_cost_anhydrous_usd_lb"
        ],
        "n_cost_uan32_usd_lb": FALLBACK_PRICES["n_cost_uan32_usd_lb"],
        "n_cost_urea_usd_lb": FALLBACK_PRICES["n_cost_urea_usd_lb"],
        "source": FALLBACK_PRICES["fertilizer_source"],
        "date": FALLBACK_PRICES["fertilizer_date"],
        "is_live": False
    }


def fetch_weather_data(county: str, state: str) -> dict:

    return _get_fallback_weather(county, state)
    """
    Fetch current growing season weather from NOAA
    Returns GDD and precipitation data
    """
    if not NOAA_KEY or NOAA_KEY == "optional_for_now":
        return _get_fallback_weather(county, state)

    try:
        # NOAA Climate Data Online API
        headers = {"token": NOAA_KEY}

        # Get station for county
        station_url = "https://www.ncdc.noaa.gov/cdo-web/api/v2/stations"
        station_params = {
            "locationid": f"FIPS:{_get_county_fips(county, state)}",
            "datasetid": "GHCND",
            "limit": 1
        }

        station_response = requests.get(
            station_url,
            headers=headers,
            params=station_params,
            timeout=5
        )

        if station_response.status_code == 200:
            stations = station_response.json().get("results", [])
            if stations:
                station_id = stations[0]["id"]

                # Get current year data
                current_year = datetime.now().year
                data_url = "https://www.ncdc.noaa.gov/cdo-web/api/v2/data"
                data_params = {
                    "datasetid": "GHCND",
                    "stationid": station_id,
                    "startdate": f"{current_year}-04-01",
                    "enddate": datetime.now().strftime("%Y-%m-%d"),
                    "datatypeid": "TMAX,TMIN,PRCP",
                    "limit": 1000,
                    "units": "standard"
                }

                data_response = requests.get(
                    data_url,
                    headers=headers,
                    params=data_params,
                    timeout=5
                )

                if data_response.status_code == 200:
                    records = data_response.json().get("results", [])
                    if records:
                        return _process_noaa_data(records, county, state)

    except Exception:
        pass

    return _get_fallback_weather(county, state)


def _process_noaa_data(records: list, county: str, state: str) -> dict:
    """Process NOAA records into GDD and precipitation"""
    total_precip = 0
    gdd_total = 0
    days_processed = 0

    tmax_by_date = {}
    tmin_by_date = {}

    for record in records:
        dtype = record.get("datatype", "")
        value = record.get("value", 0)
        date = record.get("date", "")[:10]

        if dtype == "TMAX":
            tmax_by_date[date] = value / 10  # Convert to Celsius
        elif dtype == "TMIN":
            tmin_by_date[date] = value / 10
        elif dtype == "PRCP":
            total_precip += value / 10  # Convert to mm

    # Calculate GDD (base 50°F = 10°C)
    for date in tmax_by_date:
        if date in tmin_by_date:
            tmax_f = tmax_by_date[date] * 9/5 + 32
            tmin_f = tmin_by_date[date] * 9/5 + 32
            tmax_f = min(86, tmax_f)  # Cap at 86°F
            tmin_f = max(50, tmin_f)  # Floor at 50°F
            gdd = ((tmax_f + tmin_f) / 2) - 50
            if gdd > 0:
                gdd_total += gdd
                days_processed += 1

    precip_inches = round(total_precip / 25.4, 1)

    return {
        "gdd": round(gdd_total),
        "precip_in": precip_inches,
        "days_tracked": days_processed,
        "county": county,
        "state": state,
        "source": "NOAA Climate Data Online (Live)",
        "is_live": True,
        "date": datetime.now().strftime("%Y-%m-%d")
    }


def _get_fallback_weather(county: str, state: str) -> dict:
    """Static historical weather by state"""
    state_weather = {
        "Missouri": {"gdd": 2834, "precip_in": 22.8},
        "Iowa": {"gdd": 2634, "precip_in": 28.4},
        "Illinois": {"gdd": 2712, "precip_in": 31.2},
        "Indiana": {"gdd": 2698, "precip_in": 27.3},
        "Kansas": {"gdd": 2934, "precip_in": 14.2},
        "Nebraska": {"gdd": 2812, "precip_in": 18.7},
        "Minnesota": {"gdd": 2487, "precip_in": 24.8},
        "Ohio": {"gdd": 2723, "precip_in": 26.4},
        "Kentucky": {"gdd": 2876, "precip_in": 25.1},
        "Tennessee": {"gdd": 2998, "precip_in": 23.6}
    }

    weather = state_weather.get(
        state,
        {"gdd": 2700, "precip_in": 24.0}
    )

    return {
        "gdd": weather["gdd"],
        "precip_in": weather["precip_in"],
        "county": county,
        "state": state,
        "source": f"Historical average — {state} (2024 growing season)",
        "is_live": False,
        "date": "2024 seasonal average"
    }


def _get_county_fips(county: str, state: str) -> str:
    """Get FIPS code for NOAA API lookup"""
    fips_map = {
        ("Cape Girardeau", "Missouri"): "29031",
        ("New Madrid", "Missouri"): "29143",
        ("Scott", "Missouri"): "29201",
        ("Mississippi", "Missouri"): "29133",
        ("Pemiscot", "Missouri"): "29155",
        ("Dunklin", "Missouri"): "29069",
        ("Story", "Iowa"): "19169",
        ("Hamilton", "Iowa"): "19079",
        ("Boone", "Iowa"): "19015",
        ("McLean", "Illinois"): "17113",
        ("Champaign", "Illinois"): "17019",
        ("Tippecanoe", "Indiana"): "18157",
        ("Finney", "Kansas"): "20055",
        ("Hamilton", "Nebraska"): "31079",
        ("Renville", "Minnesota"): "27143",
        ("Darke", "Ohio"): "39037",
        ("Christian", "Kentucky"): "21047",
        ("Gibson", "Tennessee"): "47053"
    }
    return fips_map.get((county, state), "29031")


def get_all_prices(state: str = "Missouri", county: str = "Cape Girardeau") -> dict:
    """
    Main price fetch function
    Returns all prices needed for prescription
    Tries live APIs first, falls back to static data
    """
    global _price_cache, _cache_timestamp

    # Return cached if still valid
    if is_cache_valid():
        return _price_cache

    # Fetch all prices
    corn_data = fetch_corn_price_usda(state)
    fertilizer_data = fetch_fertilizer_prices_usda()
    weather_data = fetch_weather_data(county, state)

    result = {
        # Corn price
        "corn_price_usd_bu": corn_data["price"],
        "corn_price_source": corn_data.get("source", "USDA AMS Corn Belt Elevator (cached)"),
        "corn_price_date": corn_data.get("date", "2026-05-19"),
        "corn_price_is_live": corn_data.get("is_live", False),

        # Fertilizer prices
        "anhydrous_ammonia_usd_ton": fertilizer_data[
            "anhydrous_ammonia_usd_ton"
        ],
        "uan_32_usd_ton": fertilizer_data["uan_32_usd_ton"],
        "urea_46_usd_ton": fertilizer_data["urea_46_usd_ton"],
        "n_cost_anhydrous_usd_lb": fertilizer_data[
            "n_cost_anhydrous_usd_lb"
        ],
        "n_cost_uan32_usd_lb": fertilizer_data["n_cost_uan32_usd_lb"],
        "n_cost_urea_usd_lb": fertilizer_data["n_cost_urea_usd_lb"],
        "fertilizer_source": fertilizer_data["source"],
        "fertilizer_date": fertilizer_data["date"],
        "fertilizer_is_live": fertilizer_data["is_live"],

        # Weather
        "gdd": weather_data["gdd"],
        "precip_in": weather_data["precip_in"],
        "weather_source": weather_data["source"],
        "weather_is_live": weather_data["is_live"],

        # Overall status
        "any_live": (
            corn_data["is_live"] or
            fertilizer_data["is_live"] or
            weather_data["is_live"]
        ),
        "all_live": (
            corn_data["is_live"] and
            fertilizer_data["is_live"] and
            weather_data["is_live"]
        ),
        "last_updated": datetime.now().isoformat()
    }

    # Cache result
    _price_cache = result
    _cache_timestamp = datetime.now()

    return result


def format_price_status(prices: dict) -> str:
    """
    Format data source status for display
    Shows farmer exactly where data came from
    """
    lines = []

    corn_icon = "🟢" if prices["corn_price_is_live"] else "🟡"
    fert_icon = "🟢" if prices["fertilizer_is_live"] else "🟡"
    weather_icon = "🟢" if prices["weather_is_live"] else "🟡"

    lines.append(
        f"{corn_icon} Corn: ${prices['corn_price_usd_bu']}/bu "
        f"— {prices['corn_price_source']}"
    )
    lines.append(
        f"{fert_icon} Nitrogen: ${prices['n_cost_anhydrous_usd_lb']}/lb "
        f"(anhydrous) — {prices['fertilizer_source']}"
    )
    lines.append(
        f"{weather_icon} Weather: {prices['gdd']} GDD, "
        f"{prices['precip_in']}\" precip "
        f"— {prices['weather_source']}"
    )

    return "\n".join(lines)