# QUANT.AI — Phase 1

A Two Sigma / Renaissance-grade stock intelligence terminal for Indian markets (NSE / BSE).
React 18 + TypeScript front end, FastAPI back end, Yahoo Finance data, Anthropic Claude analysis.

---

## What it does

- **Live price terminal** for any of 100 NSE stocks (Nifty 50 + 50 midcaps)
- **TradingView Lightweight Charts** with 6 timeframes, 3 chart types, EMA 9/20/50/200 overlays, volume histogram, OHLCV crosshair
- **Full technical signal pack**: RSI, MACD, Stoch RSI, ADX, Bollinger Bands (with squeeze detection), ATR, OBV trend, VWAP, Supertrend, EMA stack
- **Multi-factor screener** across the full 100-stock universe in 5 modes (Intraday / Short Term / Momentum / Breakout / Value) with a 0–100 score, A+ to C grade, reasons, risks
- **Claude-powered AI analyst**: structured trade plan with intraday entry / T1 / T2 / SL / R:R, short-term outlook, key reasons, key risks
- **Watchlist** with sparklines, persisted to localStorage
- **Live indices** topbar (Nifty 50, Bank Nifty, India VIX) with IST market clock

## Tech Stack

| Layer | Tech |
|-------|------|
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, Zustand, Axios, lightweight-charts v4 |
| Backend  | FastAPI, yfinance, pandas, numpy, ta (technical analysis library) |
| AI       | Anthropic Claude (`claude-sonnet-4-20250514`) |

---

## Setup

### 1. Backend

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env       # then edit and set ANTHROPIC_API_KEY
uvicorn main:app --reload --port 8000
```

Backend lives at `http://localhost:8000` — Swagger docs at `/docs`.

### 2. Frontend

```bash
cd frontend
npm install
cp .env.example .env       # default API base is http://localhost:8000
npm run dev
```

App opens at `http://localhost:5173`.

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET  | `/api/price/{symbol}`        | Price snapshot (RELIANCE.NS, TCS.NS, …) |
| GET  | `/api/chart/{symbol}`        | OHLCV bars — `?range=&interval=` |
| GET  | `/api/indicators/{symbol}`   | Full technical indicator pack |
| GET  | `/api/screener?mode=`        | Top 10 ranked stocks for the mode |
| POST | `/api/recommend`             | Claude AI recommendation |
| GET  | `/api/indices`               | Nifty / Bank Nifty / VIX |
| GET  | `/api/universe`              | Searchable 100-stock universe |

---

## Project Structure

```
quant-ai/
├── backend/
│   ├── main.py                 # FastAPI app + endpoint wiring
│   ├── data/
│   │   ├── universe.py         # 100-stock NSE universe with sectors
│   │   ├── market.py           # yfinance price + history fetchers
│   │   ├── indicators.py       # RSI / MACD / EMA / BB / ADX / ATR / OBV / Stoch RSI / VWAP / Supertrend
│   │   └── screener.py         # async parallel screener + multi-factor scoring
│   ├── ai/
│   │   └── claude.py           # Anthropic API client + structured JSON prompt
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── src/
    │   ├── components/         # Chart, SearchBar, StockHeader, SignalPanel,
    │   │                       # AIRecommendation, Screener, Watchlist, TopBar
    │   ├── store/useStore.ts   # Zustand global state
    │   ├── api/client.ts       # Axios HTTP client
    │   ├── types/index.ts      # Shared TS types
    │   ├── utils.ts            # INR / pct / IST formatters, color helpers
    │   ├── App.tsx
    │   ├── main.tsx
    │   └── index.css           # Design system (CSS variables) + Tailwind
    ├── package.json
    ├── tailwind.config.js
    ├── vite.config.ts
    └── tsconfig.json
```

---

## Scoring Algorithm (screener)

Each stock gets a 0–100 score across five factor groups:

| Group | Max | Examples |
|-------|-----|----------|
| Momentum | 25 | RSI 40-65, MACD bullish crossover, Stoch RSI > 50 |
| Trend    | 25 | Above EMA20/50/200, ADX > 25 |
| Volume   | 20 | Volume > 1.5× avg, OBV rising |
| Volatility setup | 15 | BB squeeze, manageable ATR |
| VWAP / Supertrend | 15 | (Intraday mode only) |

Mode-specific nudges further bias toward setups that suit the trader's intent (breakout, momentum, value mean-reversion, etc.).

Grade mapping: ≥80 → A+, ≥70 → A, ≥60 → B+, ≥50 → B, else C.

---

## Notes

- yfinance scans are throttled with a semaphore (max 10 concurrent) and cached per-mode for 3 minutes.
- Live price polling (15s) only runs during NSE hours (9:15–15:30 IST, weekdays).
- All errors return graceful 503s — the screener skips failed symbols rather than aborting.
