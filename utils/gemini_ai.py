"""
Google Gemini AI Integration
Generates plain English explanations for prescriptions
and professional agronomist briefs
"""

import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_API_KEY_2 = os.getenv("GOOGLE_API_KEY_2")
AVAILABLE_KEYS = [k for k in [GOOGLE_API_KEY, GOOGLE_API_KEY_2] if k]


def get_model():
    """
    Returns None to use fallback text.
    Re-enable when Gemini quota resets.
    """
    return None


def generate_prescription_explanation(
    crop: str,
    county: str,
    state: str,
    om_pct: float,
    recommended_n: float,
    current_rate: float,
    savings_usd_ac: float,
    savings_usd_total: float,
    farm_acres: float,
    soil_productivity_class: str,
    om_credit: float,
    corn_price: float,
    n_cost: float,
    confidence_level: str,
    peer_summary: str,
    warnings: list
) -> str:

    prompt = f"""
You are an agronomist explaining a nitrogen fertilizer prescription
to a farmer in plain, direct language. No jargon. No buzzwords.
Speak like a trusted advisor who respects the farmer intelligence.

PRESCRIPTION DATA:
- Farmer location: {county} County, {state}
- Crop: {crop}
- Farm size: {farm_acres} acres
- Current nitrogen rate: {current_rate} lbs/acre
- SoilProve recommendation: {recommended_n} lbs/acre
- Savings: ${savings_usd_ac:.2f}/acre = ${savings_usd_total:,.2f} total season
- Soil organic matter: {om_pct}%
- Soil productivity class: {soil_productivity_class}
- OM nitrogen credit applied: {om_credit} lbs/acre
- Current corn price: ${corn_price}/bu
- Nitrogen cost: ${n_cost}/lb
- Recommendation confidence: {confidence_level}

{peer_summary}

WARNINGS TO ADDRESS (if any):
{chr(10).join(warnings) if warnings else "None"}

Write a 3-paragraph explanation:

Paragraph 1 (Why this rate):
Explain in plain English why {recommended_n} lbs/acre is recommended
instead of {current_rate} lbs/acre. Mention the organic matter and
what it means for natural nitrogen supply. Keep it to 3-4 sentences.

Paragraph 2 (What your neighbors did):
Summarize the peer farm data in a way that removes yield fear.
Focus on what neighboring farmers achieved. Be specific with numbers.
3-4 sentences.

Paragraph 3 (What this means for your farm):
State the total season savings clearly. Mention the confidence level
honestly. End with one sentence recommending they share this with
their agronomist. 2-3 sentences.

Keep total response under 200 words.
Use farmer-friendly language throughout.
Never use the words: algorithm, AI, machine learning, model, optimize.
"""

    try:
        m = get_model()
        if not m:
            raise Exception("No API key available")
        response = m.generate_content(
    prompt,
    request_options={"timeout": 10}
)
        return response.text.strip()
    except Exception:
        return _fallback_explanation(
            crop, county, state, om_pct,
            recommended_n, current_rate,
            savings_usd_ac, savings_usd_total,
            om_credit, confidence_level
        )


def generate_agronomist_brief(
    farmer_name: str,
    agronomist_name: str,
    farm_acres: float,
    county: str,
    state: str,
    crop: str,
    rotation: str,
    om_pct: float,
    soil_series: str,
    current_rate: float,
    recommended_n: float,
    range_low: float,
    range_high: float,
    savings_usd_ac: float,
    savings_usd_total: float,
    corn_price: float,
    n_cost: float,
    confidence_level: str,
    peer_summary: str,
    warnings: list
) -> str:

    prompt = f"""
Write a professional but concise email from a farmer to their agronomist
sharing a nitrogen prescription for review.

FARMER: {farmer_name}
AGRONOMIST: {agronomist_name}
FARM: {farm_acres} acres, {county} County, {state}
CROP: {crop} ({rotation.replace("_", " ")})
SOIL: {soil_series}, {om_pct}% organic matter

PRESCRIPTION DETAILS:
- Current practice: {current_rate} lbs N/acre (flat rate)
- SoilProve recommendation: {recommended_n} lbs N/acre
- Recommended range: {range_low} - {range_high} lbs N/acre
- Methodology: MRTN (University of Illinois / Iowa State Extension)
- Confidence level: {confidence_level}
- Projected savings: ${savings_usd_ac:.2f}/acre = ${savings_usd_total:,.2f} season
- Corn price used: ${corn_price}/bu
- N cost used: ${n_cost}/lb

PEER VALIDATION:
{peer_summary}

WARNINGS:
{chr(10).join(warnings) if warnings else "None"}

Write a professional email with:
1. Polite greeting addressing the agronomist by name
2. Brief context (farm, crop, situation)
3. Clear statement of the prescription and methodology used
4. Summary of peer farm validation data
5. Specific request for agronomist review and professional opinion
6. Professional closing

Tone: Respectful, data-driven, collaborative.
The farmer wants the agronomist input - not to replace them.
Length: 250-300 words maximum.
Format as a proper email with Subject line.
"""

    try:
        m = get_model()
        if not m:
            raise Exception("No API key available")
        response = m.generate_content(
            prompt,
            request_options={"timeout": 5}
      )
        return response.text.strip()
    except Exception:
        return _fallback_agronomist_brief(
            farmer_name, agronomist_name,
            county, state, crop,
            recommended_n, current_rate,
            savings_usd_ac, savings_usd_total,
            confidence_level
        )


def generate_outcome_analysis(
    county: str,
    state: str,
    crop: str,
    prescribed_n: float,
    actual_n: float,
    actual_yield: float,
    historical_avg_yield: float,
    cost_saved_usd_ac: float,
    farm_acres: float,
    weather_normal: bool
) -> str:

    followed_prescription = abs(actual_n - prescribed_n) <= 5
    yield_change = actual_yield - historical_avg_yield

    prompt = f"""
Write a brief harvest outcome analysis for a corn farmer.
Plain language. Data-driven. Honest.

OUTCOME DATA:
- Location: {county} County, {state}
- Crop: {crop}
- Prescribed N rate: {prescribed_n} lbs/acre
- Actual N applied: {actual_n} lbs/acre
- Followed prescription: {followed_prescription}
- Actual yield: {actual_yield} bu/acre
- Historical average yield: {historical_avg_yield} bu/acre
- Yield change: {yield_change:+.1f} bu/acre
- Cost saved: ${cost_saved_usd_ac:.2f}/acre
- Total season savings: ${cost_saved_usd_ac * farm_acres:,.2f}
- Weather: {'Normal season' if weather_normal else 'Abnormal weather'}

Write 2 paragraphs:

Paragraph 1: What happened this season
State the results clearly and honestly. 3 sentences.

Paragraph 2: What this means going forward
Explain what this data tells us. Note that their data helps other farmers.
Recommend next steps. 3 sentences.

Keep total under 120 words.
Be honest - do not spin negative results positively.
"""

    try:
        m = get_model()
        if not m:
            raise Exception("No API key available")
        response = m.generate_content(prompt)
        return response.text.strip()
    except Exception:
        return _fallback_outcome_analysis(
            prescribed_n, actual_n,
            actual_yield, historical_avg_yield,
            cost_saved_usd_ac, farm_acres
        )


def _fallback_explanation(
    crop, county, state, om_pct,
    recommended_n, current_rate,
    savings_usd_ac, savings_usd_total,
    om_credit, confidence_level
) -> str:
    direction = "reducing" if recommended_n < current_rate else "increasing"
    diff = abs(recommended_n - current_rate)
    return (
        f"Based on your soil data and current market prices, we recommend "
        f"{direction} your nitrogen application from {current_rate:.1f} to "
        f"{recommended_n} lbs/acre — a difference of {diff:.0f} lbs/acre. "
        f"Your soil organic matter of {om_pct}% is a key factor in this "
        f"recommendation. Higher organic matter naturally releases nitrogen "
        f"as it breaks down, reducing how much synthetic nitrogen your crop "
        f"needs. The MRTN methodology from University of Illinois and Iowa "
        f"State accounts for this with a credit of {abs(om_credit):.0f} lbs/acre.\n\n"
        f"{'At current prices, this prescription saves $' + f'{savings_usd_ac:.2f}' + ' per acre' if savings_usd_ac >= 0 else 'Note: this prescription recommends increasing your rate, which will cost an additional $' + f'{abs(savings_usd_ac):.2f}' + ' per acre but is expected to protect or improve yield'} "
        f"— a total impact of ${abs(savings_usd_total):,.2f} this season. "
        f"Confidence level: {confidence_level}. We recommend sharing this "
        f"prescription with your agronomist before application."
    )


def _fallback_agronomist_brief(
    farmer_name, agronomist_name,
    county, state, crop,
    recommended_n, current_rate,
    savings_usd_ac, savings_usd_total,
    confidence_level
) -> str:
    return (
        f"Subject: Nitrogen Prescription Review Request — "
        f"{county} County {crop.title()}\n\n"
        f"Dear {agronomist_name},\n\n"
        f"I hope this message finds you well. I am writing to share a "
        f"nitrogen prescription generated by SoilProve for my {crop} "
        f"operation in {county} County, {state}, and to request your "
        f"professional review before I finalize my spring application plan.\n\n"
        f"The SoilProve prescription recommends {recommended_n} lbs N/acre, "
        f"compared to my current practice of {current_rate} lbs N/acre. "
        f"This recommendation is based on the MRTN methodology developed "
        f"by University of Illinois and Iowa State University Extension, "
        f"adjusted for my soil organic matter and current market prices.\n\n"
        f"The projected savings are ${savings_usd_ac:.2f}/acre, totaling "
        f"${savings_usd_total:,.2f} for the season. The recommendation "
        f"confidence level is {confidence_level}.\n\n"
        f"I would greatly value your professional opinion on whether this "
        f"rate is appropriate for my specific fields and soil conditions. "
        f"I trust your expertise and want to make sure any changes to my "
        f"fertilizer program have your input.\n\n"
        f"Please let me know if you would like to review the full "
        f"prescription data or discuss further.\n\n"
        f"Thank you for your continued guidance.\n\n"
        f"Sincerely,\n{farmer_name}"
    )


def _fallback_outcome_analysis(
    prescribed_n, actual_n,
    actual_yield, historical_avg_yield,
    cost_saved_usd_ac, farm_acres
) -> str:
    yield_change = actual_yield - historical_avg_yield
    direction = "above" if yield_change >= 0 else "below"
    return (
        f"Your {actual_yield} bu/acre yield came in "
        f"{abs(yield_change):.1f} bu/acre {direction} your historical "
        f"average of {historical_avg_yield} bu/acre. You applied "
        f"{actual_n} lbs N/acre. "
        f"Total season savings: ${abs(cost_saved_usd_ac * farm_acres):,.2f} "
        f"compared to the county average application rate.\n\n"
        f"Your outcome data has been added to the peer pool to help other "
        f"farmers in your region make more confident decisions next season."
    )