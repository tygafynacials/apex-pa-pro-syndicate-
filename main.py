from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
import pandas as pd
import io
from app.providers.deriv import DerivProvider
from app.strategy import analyze_price_action

app = FastAPI(title="APEX PA Signal Generator", version="0.1.0")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
deriv = DerivProvider()

class AnalyzeRequest(BaseModel):
    symbol: str = "EURUSD"
    timeframe: str = "M15"
    candles: list[dict]
    min_score: int = 75

@app.get("/", response_class=HTMLResponse)
async def home():
    with open("app/static/index.html", encoding="utf-8") as f:
        return f.read()

@app.get("/api/health")
async def health():
    return {"status": "ok", "app": "APEX PA", "mode": "signal-only prototype"}

@app.get("/api/markets")
async def markets():
    try:
        return await deriv.active_symbols()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not load Deriv markets: {exc}")

@app.get("/api/candles")
async def candles(symbol: str, granularity: int = 900, count: int = 300):
    if granularity not in {60,120,180,300,600,900,1800,3600,7200,14400,28800,86400}:
        raise HTTPException(status_code=400, detail="Unsupported candle granularity")
    count = max(60, min(count, 5000))
    try:
        return await deriv.candles(symbol, granularity, count)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not load candles: {exc}")

@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest):
    try:
        df = pd.DataFrame(req.candles)
        signal = analyze_price_action(df, req.symbol, req.timeframe, min_score=req.min_score)
        return {"signal": signal, "message": "No qualified setup on the latest candle." if signal is None else "Candidate setup found."}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.post("/api/analyze-csv")
async def analyze_csv(file: UploadFile = File(...), symbol: str = "CSV-MARKET", timeframe: str = "M15", min_score: int = 75):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file.")
    raw = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(raw))
        df.columns = [c.strip().lower() for c in df.columns]
        required = {"open", "high", "low", "close"}
        if not required.issubset(df.columns):
            raise ValueError("CSV must include open, high, low, close columns.")
        signal = analyze_price_action(df, symbol, timeframe, min_score=min_score)
        return {"signal": signal, "message": "No qualified setup on the latest candle." if signal is None else "Candidate setup found."}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"CSV analysis failed: {exc}")
