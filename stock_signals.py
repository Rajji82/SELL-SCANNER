"""Closed NSE intraday candles and EMA20 crossover signals for Excel."""

import datetime as dt
import math

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
ALPHA = 2 / 21
MIN_BARS = 100


def closed_bars(candles, now, interval):
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

    return sorted(by_start.items())


def crossover(previous_close, previous_ema, close, ema):
    if previous_close <= previous_ema and close > ema:
        return "BUY"
    if previous_close >= previous_ema and close < ema:
        return "SELL"
    return "WAIT"


def signal_from_candles(candles, now, minutes=5):
    """Ignore open bars and require consecutive bars for an entry/exit alert."""
    interval = dt.timedelta(minutes=minutes)
    bars = closed_bars(candles, now, interval)
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
    else:
        signal = crossover(previous_close, ema, close, current_ema)

    return {
        "candle_end_ist": ended.isoformat(timespec="minutes"),
        "prev_close": previous_close,
        "prev_ema20": ema,
        "close": close,
        "ema20": current_ema,
        "signal": signal,
        "status": status,
    }


def daily_signal_history(candles, now, report_days):
    """Reconstruct 15-minute crossovers and grade the next same-session close."""
    interval = dt.timedelta(minutes=15)
    bars = closed_bars(candles, now, interval)
    if len(bars) < MIN_BARS:
        return None

    first_date = now.date() - dt.timedelta(days=report_days - 1)
    previous_start, previous_close = bars[0]
    ema = previous_close
    results = []
    for index, (start, close) in enumerate(bars[1:], start=1):
        next_ema = ema + ALPHA * (close - ema)
        if (index >= MIN_BARS - 1 and start.date() >= first_date
                and start - previous_start == interval):
            signal = crossover(previous_close, ema, close, next_ema)
            if signal != "WAIT":
                next_start, next_close = bars[index + 1] if index + 1 < len(bars) else (None, None)
                outcome = "PENDING"
                if next_start == start + interval and next_start.date() == start.date():
                    hit = next_close > close if signal == "BUY" else next_close < close
                    outcome = "HIT" if hit else "MISS"
                else:
                    next_close = None
                results.append({
                    "trade_date": start.date().isoformat(),
                    "candle_end_ist": (start + interval).isoformat(timespec="minutes"),
                    "signal": signal,
                    "event_close": close,
                    "next_close": next_close,
                    "outcome": outcome,
                })
        previous_start, previous_close, ema = start, close, next_ema
    return results
