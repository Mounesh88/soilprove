# SoilProve — Precision Nitrogen & Fertilizer Optimization

> Better nitrogen decisions start with someone who isn't selling you fertilizer.

## The Problem

Corn Belt farmers spend $100,000+ every season on nitrogen fertilizer using flat rates from agronomists with financial ties to fertilizer retailers. They have soil tests proving field variability exists. Their equipment can apply variable rates. But they never act — because one bad yield year costs more than they save.

**Result: $15-30 per acre wasted on every farm, every season across 90 million US corn acres.**

## The Solution

SoilProve generates field-specific nitrogen prescriptions using:

1. **MRTN Methodology** — University of Illinois and Iowa State Extension validated model
2. **Peer Validation** — verified outcomes from neighboring farms with same soil profile
3. **Outcome Tracking** — harvest data builds the peer pool every season

## Features

- Field-specific nitrogen prescription for 6 crops (Corn, Soybeans, Wheat, Sorghum, Cotton, Rice)
- 10 Corn Belt states coverage
- Live USDA corn and fertilizer price data
- Peer farm similarity matching with match scores
- Interactive map of peer farm locations
- AI-generated plain English explanation (Google Gemini)
- Professional agronomist brief ready to email
- Harvest outcome tracker with database persistence
- Price sensitivity analysis

## Technology Stack

- **Backend:** Python, FastAPI, Uvicorn
- **Frontend:** HTML, CSS, JavaScript, Leaflet.js
- **AI:** Google Gemini API
- **Data:** USDA NASS API, USDA AMS, NOAA, USDA SSURGO
- **Methodology:** MRTN (Sawyer et al. 2006 — University of Illinois)

## Setup

1. Clone the repository
2. Install dependencies: