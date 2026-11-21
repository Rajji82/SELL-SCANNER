"""Closed NSE intraday candles and EMA20 crossover signals for Excel."""

import datetime as dt
import math

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
ALPHA = 2 / 21
MIN_BARS = 100


def signal_from_candles(candles, now, minutes=5):
    """Ignore open bars and require consecutive bars for an entry/exit alert."""
    interval = dt.timedelta(minutes=minutes)
    by_start = {}
    for candle in candles:
        try:
            start = dt.datetime.fromisoformat(candle[0])
            start = start.replace(tzinfo=IST) if start.tzinfo is None else start.astimezone(IST)
            close = float(candle[4])
        except (IndexError, TypeError, ValueError):
            continue
        if start + interval <= now and math.isfinite(close) and close > 0:
            by_start[start] = close

    bars = sorted(by_start.items())
    if len(bars) < MIN_BARS:
        return {"signal": "NEED DATA", "status": "Insufficient closed candles"}

    previous_start, previous_close = bars[-2]
    start, close = bars[-1]
    ema = bars[0][1]
    for _, price in bars[1:-1]:
        ema += ALPHA * (price - ema)

    current_ema = ema + ALPHA * (close - ema)
    ended = start + interval
    signal = "WAIT"
    status = "OK"
    if now - ended >= interval:
        signal, status = "STALE", "No recent closed candle"
    elif start - previous_start != interval:
        signal, status = "NEED DATA", "Previous consecutive candle missing"
    elif previous_close <= ema and close > current_ema:
        signal = "BUY"
    elif previous_close >= ema and close < current_ema:
        signal = "SELL"

    return {
        "candle_end_ist": ended.isoformat(timespec="minutes"),
        "prev_close": previous_close,
        "prev_ema20": ema,
        "close": close,
        "ema20": current_ema,
        "signal": signal,
        "status": status,
    }
