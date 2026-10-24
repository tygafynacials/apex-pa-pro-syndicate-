from typing import Optional
import pandas as pd

REQUIRED = {"open", "high", "low", "close"}

def analyze_price_action(
    candles: pd.DataFrame,
    symbol: str = "UNKNOWN",
    timeframe: str = "M15",
    swing_window: int = 3,
    min_score: int = 75,
    rr_targets: tuple = (1.0, 2.0, 3.0),
    atr_period: int = 14,
    min_stop_atr: float = 0.2,
    max_stop_atr: float = 3.0,
) -> Optional[dict]:
    """Evaluate the latest closed OHLC candle for a conservative candidate setup.

    This is a prototype rule set, not a validated SMC engine. Swing points are
    confirmed only after the right-hand candles exist. For live use, ensure the
    latest candle is closed and avoid look-ahead bias in any backtest.
    """
    if not REQUIRED.issubset(candles.columns):
        raise ValueError("Candles must include open, high, low, close.")
    if len(candles) < max(60, atr_period + swing_window * 2 + 5):
        return None

    df = candles.copy().reset_index(drop=True)
    for col in REQUIRED:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=list(REQUIRED)).reset_index(drop=True)
    if len(df) < max(60, atr_period + swing_window * 2 + 5):
        return None

    prev_close = df.close.shift(1)
    tr = pd.concat([(df.high-df.low), (df.high-prev_close).abs(), (df.low-prev_close).abs()], axis=1).max(axis=1)
    df["atr"] = tr.rolling(atr_period).mean()
    w = swing_window
    df["swing_high"] = False
    df["swing_low"] = False

    # Only candles with a full left/right window can be confirmed swing points.
    for i in range(w, len(df)-w):
        hi = df.high.iloc[i-w:i+w+1]
        lo = df.low.iloc[i-w:i+w+1]
        if df.high.iloc[i] == hi.max():
            df.loc[i, "swing_high"] = True
        if df.low.iloc[i] == lo.min():
            df.loc[i, "swing_low"] = True

    # Latest candle is tested; prior swing points must have been confirmed earlier.
    last = df.iloc[-1]
    prev = df.iloc[-2]
    hist = df.iloc[:-1]
    sh = hist[hist.swing_high]
    sl = hist[hist.swing_low]
    if sh.empty or sl.empty:
        return None

    recent_sh, recent_sl = sh.tail(2), sl.tail(2)
    bullish_structure = len(recent_sh) == 2 and len(recent_sl) == 2 and recent_sh.high.iloc[-1] > recent_sh.high.iloc[-2] and recent_sl.low.iloc[-1] > recent_sl.low.iloc[-2]
    bearish_structure = len(recent_sh) == 2 and len(recent_sl) == 2 and recent_sh.high.iloc[-1] < recent_sh.high.iloc[-2] and recent_sl.low.iloc[-1] < recent_sl.low.iloc[-2]

    # Use most recent confirmed swing levels as the sweep reference.
    swing_high = float(sh.high.iloc[-1])
    swing_low = float(sl.low.iloc[-1])
    close = float(last.close)
    atr = float(last.atr) if pd.notna(last.atr) else 0.0
    if atr <= 0:
        return None

    bull_sweep = float(last.low) < swing_low and close > swing_low
    bear_sweep = float(last.high) > swing_high and close < swing_high

    # Engulfing candle confirmation.
    bull_engulf = prev.close < prev.open and last.close > last.open and last.open <= prev.close and last.close >= prev.open
    bear_engulf = prev.close > prev.open and last.close < last.open and last.open >= prev.close and last.close <= prev.open

    # A structure break must cross a prior swing that existed before the current candle.
    bull_break = close > swing_high
    bear_break = close < swing_low

    direction, reasons, score = None, [], 0
    entry = close
    if bull_sweep and bull_break and bull_engulf:
        direction = "BUY"
        reasons = ["Bullish liquidity sweep", "Bullish structure break", "Bullish engulfing candle"]
        score += 20 + 20 + 15
        if bullish_structure:
            score += 20
            reasons.append("Bullish swing structure")
        stop = float(last.low) - 0.1 * atr
        risk = entry - stop
    elif bear_sweep and bear_break and bear_engulf:
        direction = "SELL"
        reasons = ["Bearish liquidity sweep", "Bearish structure break", "Bearish engulfing candle"]
        score += 20 + 20 + 15
        if bearish_structure:
            score += 20
            reasons.append("Bearish swing structure")
        stop = float(last.high) + 0.1 * atr
        risk = stop - entry
    else:
        return None

    if risk <= 0 or risk < min_stop_atr * atr or risk > max_stop_atr * atr:
        return None

    score += 10  # Risk/reward geometry passes; this is not a win probability.
    if score < min_score:
        return None

    if direction == "BUY":
        targets = [entry + r*risk for r in rr_targets]
    else:
        targets = [entry - r*risk for r in rr_targets]

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry": round(entry, 8),
        "stop_loss": round(stop, 8),
        "tp1": round(targets[0], 8),
        "tp2": round(targets[1], 8),
        "tp3": round(targets[2], 8),
        "risk_distance": round(risk, 8),
        "score": min(int(score), 100),
        "reasons": reasons,
        "status": "CANDIDATE — requires backtesting",
        "generated_from": "latest supplied candle"
    }
