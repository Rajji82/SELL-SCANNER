"""Option-selling scanner (Angel One SmartAPI) with Advanced POP, IVR, 1-SD & Technical Filters."""
import os, time, threading, math, datetime as dt
import requests, pyotp
from SmartApi import SmartConnect
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse

load_dotenv()
API_KEY = os.environ["ANGEL_API_KEY"]
CLIENT = os.environ["ANGEL_CLIENT_ID"]
PIN = os.environ["ANGEL_PIN"]
TOTP_SECRET = os.environ["ANGEL_TOTP_SECRET"]
APP_TOKEN = os.getenv("APP_TOKEN", "")

DELTA_MIN, DELTA_MAX = 0.10, 0.25
MAX_SPREAD_PCT = 5.0
MIN_OI, MIN_VOL = 1000, 100
SL_MULTIPLE = 2.0
EVENTS = {}  # Jaise: {"TCS": "2026-11-15"}

MASTER_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
INDEX_TOKENS = {"NIFTY": "99926000", "BANKNIFTY": "99926009"}

_lock = threading.Lock()
_api = None
_master = {"day": None, "rows": []}
_historical_cache = {}


def api():
    global _api
    with _lock:
        if _api is None:
            o = SmartConnect(api_key=API_KEY)
            r = o.generateSession(CLIENT, PIN, pyotp.TOTP(TOTP_SECRET).now())
            if not r.get("status"):
                raise RuntimeError(f"Login fail: {r.get('message')}")
            _api = o
        return _api


def reset_session():
    global _api
    with _lock:
        _api = None


def master():
    today = dt.date.today()
    if _master["day"] != today:
        raw = requests.get(MASTER_URL, timeout=90).json()
        _master["rows"] = [
            r for r in raw
            if (r["exch_seg"] == "NFO" and r["instrumenttype"] in ("OPTSTK", "OPTIDX"))
            or (r["exch_seg"] == "NSE" and r["symbol"].endswith("-EQ"))
        ]
        _master["day"] = today
    return _master["rows"]


def parse_date(s):
    return dt.datetime.strptime(s.title(), "%d%b%Y").date()


def pick_expiry(rows, sym, min_days):
    exps = sorted({parse_date(r["expiry"]) for r in rows if r["exch_seg"] == "NFO" and r["name"] == sym})
    ok = [e for e in exps if (e - dt.date.today()).days >= min_days]
    return ok[0] if ok else None


def get_token_for_symbol(rows, sym):
    if sym in INDEX_TOKENS:
        return INDEX_TOKENS[sym], "NSE"
    m = [r for r in rows if r["exch_seg"] == "NSE" and r["name"] == sym and r["symbol"].endswith("-EQ")]
    if not m:
        raise ValueError(f"{sym} ka NSE token nahi mila")
    return m[0]["token"], "NSE"


def get_spot(a, rows, sym):
    tok, seg = get_token_for_symbol(rows, sym)
    d = a.getMarketData("LTP", {seg: [tok]})
    return float(d["data"]["fetched"][0]["ltp"])


def get_technical_and_vol_stats(a, rows, sym):
    """Calculates 20 EMA, IV Rank & IV Percentile baseline using 1-year candles"""
    today = dt.date.today()
    if sym in _historical_cache and _historical_cache[sym]["date"] == today:
        return _historical_cache[sym]

    try:
        tok, seg = get_token_for_symbol(rows, sym)
        from_d = (today - dt.timedelta(days=365)).strftime("%Y-%m-%d 09:15")
        to_d = today.strftime("%Y-%m-%d 15:30")
        res = a.getCandleData({
            "exchange": seg,
            "symboltoken": tok,
            "interval": "ONE_DAY",
            "fromdate": from_d,
            "todate": to_d
        })
        candles = res.get("data") or []
        if len(candles) >= 30:
            closes = [float(c[4]) for c in candles]
            # Calculate 20 EMA
            k = 2 / (20 + 1)
            ema = closes[0]
            for c in closes[1:]:
                ema = (c * k) + (ema * (1 - k))
            
            # Calculate Historical Volatility for IVR/IVP
            returns = []
            for i in range(1, len(closes)):
                if closes[i-1] > 0 and closes[i] > 0:
                    returns.append(math.log(closes[i] / closes[i-1]))
            
            hv_series = []
            window = 20
            for i in range(window, len(returns)):
                sub = returns[i - window:i]
                mean = sum(sub) / window
                variance = sum((x - mean) ** 2 for x in sub) / (window - 1)
                daily_std = math.sqrt(variance)
                hv_series.append(daily_std * math.sqrt(252) * 100)

            min_v = min(hv_series) if hv_series else 15.0
            max_v = max(hv_series) if hv_series else 45.0
            
            _historical_cache[sym] = {
                "date": today,
                "ema20": round(ema, 2),
                "min_iv": min_v,
                "max_iv": max_v,
                "series": sorted(hv_series)
            }
            return _historical_cache[sym]
    except Exception:
        pass

    fallback = {"date": today, "ema20": 0.0, "min_iv": 15.0, "max_iv": 45.0, "series": []}
    _historical_cache[sym] = fallback
    return fallback


def calculate_ivr_ivp(current_iv, stats):
    if not stats or current_iv <= 0:
        return 50.0, 50.0
    min_iv = stats.get("min_iv", 15.0)
    max_iv = stats.get("max_iv", 45.0)
    series = stats.get("series", [])

    if max_iv <= min_iv:
        ivr = 50.0
    else:
        ivr = max(0.0, min(100.0, ((current_iv - min_iv) / (max_iv - min_iv)) * 100))

    if series:
        count_less = sum(1 for v in series if v < current_iv)
        ivp = (count_less / len(series)) * 100
    else:
        ivp = ivr
    return round(ivr, 1), round(ivp, 1)


def scan_symbol(sym, min_days=3):
    a, rows = api(), master()
    exp = pick_expiry(rows, sym, min_days)
    if not exp:
        return {"symbol": sym, "error": "expiry nahi mili (symbol sahi hai?)"}
    es = exp.strftime("%d%b%Y").upper()
    spot = get_spot(a, rows, sym)
    days_to_exp = max(1, (exp - dt.date.today()).days)
    time.sleep(1.1)

    tech_stats = get_technical_and_vol_stats(a, rows, sym)
    ema20 = tech_stats.get("ema20", 0.0)

    greeks = a.optionGreek({"name": sym, "expirydate": es}).get("data") or []
    tokens = {}
    for r in rows:
        if r["exch_seg"] == "NFO" and r["name"] == sym and r["expiry"].upper() == es:
            tokens[(round(float(r["strike"]) / 100, 2), r["symbol"][-2:])] = r

    cand = []
    for g in greeks:
        d = abs(float(g["delta"]))
        if DELTA_MIN <= d <= DELTA_MAX:
            m = tokens.get((round(float(g["strikePrice"]), 2), g["optionType"]))
            if m:
                cand.append((g, d, m))

    quotes = {}
    for i in range(0, len(cand), 50):
        part = cand[i:i + 50]
        r = a.getMarketData("FULL", {"NFO": [m["token"] for _, _, m in part]})
        for f in (r.get("data") or {}).get("fetched", []):
            quotes[f["symbolToken"]] = f
        time.sleep(1.1)

    warn = []
    ev = EVENTS.get(sym)
    if ev and dt.date.fromisoformat(ev) <= exp:
        warn.append(f"⚠️ Event Alert: {ev} par corporate event/result hai! Gap risk high hai.")

    picks = []
    for g, d, m in cand:
        f = quotes.get(m["token"])
        if not f:
            continue
        ltp = float(f.get("ltp") or 0)
        oi = int(f.get("opnInterest") or 0)
        vol = int(f.get("tradeVolume") or 0)
        dep = f.get("depth") or {}
        bid = float(((dep.get("buy") or [{}])[0]).get("price") or 0)
        ask = float(((dep.get("sell") or [{}])[0]).get("price") or 0)
        if ltp <= 0 or bid <= 0 or ask <= 0:
            continue
        spread = (ask - bid) / ((ask + bid) / 2) * 100
        if spread > MAX_SPREAD_PCT or oi < MIN_OI or vol < MIN_VOL:
            continue
        k, typ, lot = float(g["strikePrice"]), g["optionType"], int(m["lotsize"])
        
        # 1. POP & POT Calculation
        pop = round((1 - d) * 100, 1)
        pot = round(min(100.0, 2 * d * 100), 1)  # Probability of touching strike before expiry
        
        # 2. IV Rank & IV Percentile
        iv = round(float(g.get("impliedVolatility") or 0), 1)
        ivr, ivp = calculate_ivr_ivp(iv, tech_stats)

        # 3. 1-Standard Deviation & Expected Move
        exp_move = round(spot * (iv / 100) * math.sqrt(days_to_exp / 365), 2)
        upper_sd = round(spot + exp_move, 2)
        lower_sd = round(spot - exp_move, 2)
        
        is_outside_sd = (typ == "CE" and k > upper_sd) or (typ == "PE" and k < lower_sd)

        # 4. Technical / Trend Confirmation with 20 EMA
        tech_note = ""
        if ema20 > 0:
            if typ == "CE" and spot < ema20:
                tech_note = "Trend Down: CE Safe"
            elif typ == "PE" and spot > ema20:
                tech_note = "Trend Up: PE Safe"
            elif typ == "CE" and spot > ema20:
                tech_note = "Bullish momentum: Watch CE"
            elif typ == "PE" and spot < ema20:
                tech_note = "Bearish momentum: Watch PE"

        prem_pct = ltp / spot * 100
        picks.append({
            "contract": f"{sym} {k:g} {typ}", "type": typ, "strike": k, "ltp": round(ltp, 2),
            "pop": pop, "pot": pot, "delta": round(d, 2), "iv": iv,
            "ivr": ivr, "ivp": ivp,
            "exp_move": exp_move, "is_outside_sd": is_outside_sd,
            "sd_boundary": upper_sd if typ == "CE" else lower_sd,
            "tech_note": tech_note,
            "dist_pct": round(abs(k - spot) / spot * 100, 2),
            "lot": lot, "premium_lot": round(ltp * lot, 2),
            "sl_price": round(ltp * SL_MULTIPLE, 2),
            "loss_at_sl": round(ltp * (SL_MULTIPLE - 1) * lot, 2),
            "breakeven": round(k - ltp if typ == "PE" else k + ltp, 2),
            "oi": oi, "vol": vol, "spread_pct": round(spread, 2),
            "score": round((pop / 100 * prem_pct) * (1 + (ivr / 100)), 3),
        })
    picks.sort(key=lambda p: p["score"], reverse=True)
    return {"symbol": sym, "spot": spot, "expiry": exp.isoformat(), "days": days_to_exp,
            "ema20": ema20, "warnings": warn, "picks": picks[:8]}


app = FastAPI()


@app.get("/api/scan")
def scan(symbols: str = "NIFTY,BANKNIFTY", min_days: int = 3, x_key: str = Header(default="")):
    if APP_TOKEN and x_key != APP_TOKEN:
        raise HTTPException(401, "galat password")
    out = []
    for sym in [s.strip().upper() for s in symbols.split(",") if s.strip()][:10]:
        try:
            with _scan_lock:
                out.append(scan_symbol(sym, min_days))
        except Exception as e:
            reset_session()
            out.append({"symbol": sym, "error": str(e)[:200]})
    return {"time": dt.datetime.now().strftime("%H:%M:%S"), "results": out}


@app.get("/")
def home():
    return FileResponse(os.path.join(os.path.dirname(__file__), "index.html"))


AUTO_TOP_N = int(os.getenv("AUTO_TOP_N", "20"))
_scan_lock = threading.Lock()
_auto_lock = threading.Lock()
_auto = {"running": False, "done": 0, "total": 0, "updated": None, "ts": None, "picks": [], "errors": []}


def fno_universe(top_n):
    a, rows = api(), master()
    names = {r["name"] for r in rows if r["exch_seg"] == "NFO" and r["instrumenttype"] == "OPTSTK"}
    eq = {r["name"]: r["token"] for r in rows
          if r["exch_seg"] == "NSE" and r["symbol"].endswith("-EQ") and r["name"] in names}
    inv = {t: n for n, t in eq.items()}
    toks, vals = list(eq.values()), []
    for i in range(0, len(toks), 50):
        r = a.getMarketData("FULL", {"NSE": toks[i:i + 50]})
        for f in (r.get("data") or {}).get("fetched", []):
            n = inv.get(f["symbolToken"])
            if n:
                vals.append((float(f.get("ltp") or 0) * float(f.get("tradeVolume") or 0), n))
        time.sleep(1.1)
    vals.sort(reverse=True)
    return [n for _, n in vals[:top_n]]


def _auto_run():
    try:
        syms = ["NIFTY", "BANKNIFTY"] + fno_universe(AUTO_TOP_N)
        _auto.update(total=len(syms), done=0, picks=[], errors=[])
        allp = []
        for s in syms:
            try:
                with _scan_lock:
                    r = scan_symbol(s)
                if r.get("error"):
                    _auto["errors"].append(f"{s}: {r['error']}")
                for p in r.get("picks", [])[:3]:
                    allp.append({**p, "symbol": s, "spot": r["spot"], "expiry": r["expiry"],
                                 "days": r["days"], "warnings": r["warnings"]})
            except Exception as e:
                reset_session()
                _auto["errors"].append(f"{s}: {str(e)[:80]}")
            _auto["done"] += 1
            _auto["picks"] = sorted(allp, key=lambda p: p["score"], reverse=True)[:25]
        _auto["updated"] = dt.datetime.now().strftime("%d-%b %H:%M:%S")
    except Exception as e:
        reset_session()
        _auto["errors"].append(str(e)[:150])
    finally:
        _auto["running"] = False


@app.get("/api/auto")
def auto(refresh: bool = False, x_key: str = Header(default="")):
    if APP_TOKEN and x_key != APP_TOKEN:
        raise HTTPException(401, "galat password")
    with _auto_lock:
        old = _auto["ts"] is None or time.time() - _auto["ts"] > 900
        if not _auto["running"] and (refresh or old):
            _auto.update(running=True, ts=time.time())
            threading.Thread(target=_auto_run, daemon=True).start()
    return {k: _auto[k] for k in ("running", "done", "total", "updated", "picks", "errors")}


# ---- Automated Historical Backtest Endpoint ----
@app.post("/api/backtest")
def calculate_pnl(data: dict, x_key: str = Header(default="")):
    if APP_TOKEN and x_key != APP_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    symbol = str(data.get("symbol", "NIFTY")).strip().upper()
    strike = float(data.get("strike", 0))
    entry_premium = float(data.get("entry_premium", 0))
    expiry_date_str = data.get("expiry_date", "")
    option_type = data.get("option_type", "CE").upper()
    lot_size = int(data.get("lot_size", 1))
    manual_expiry_price = data.get("expiry_price")

    closing_price = None

    if manual_expiry_price not in (None, ""):
        closing_price = float(manual_expiry_price)
    elif expiry_date_str:
        try:
            a, rows = api(), master()
            token, seg = get_token_for_symbol(rows, symbol)
            
            c_params = {
                "exchange": seg,
                "symboltoken": token,
                "interval": "ONE_DAY",
                "fromdate": f"{expiry_date_str} 09:15",
                "todate": f"{expiry_date_str} 15:30"
            }
            res = a.getCandleData(c_params)
            candles = res.get("data") or []
            if candles:
                closing_price = float(candles[-1][4])
        except Exception as e:
            reset_session()
            return {"status": "error", "message": f"Historical data fetch nahi hua: {str(e)}"}

    if closing_price is None:
        return {"status": "error", "message": "Expiry date ka closing data nahi mila. Expiry/CMP Price manually daalein."}

    if option_type == "CE":
        intrinsic_val = max(0.0, closing_price - strike)
    else:
        intrinsic_val = max(0.0, strike - closing_price)

    pnl_per_share = entry_premium - intrinsic_val
    total_pnl = round(pnl_per_share * lot_size, 2)
    roi_pct = round((pnl_per_share / entry_premium) * 100, 2) if entry_premium > 0 else 0.0

    return {
        "status": "success",
        "symbol": symbol,
        "strike": strike,
        "entry_premium": entry_premium,
        "expiry_price": round(closing_price, 2),
        "intrinsic_value": round(intrinsic_val, 2),
        "pnl_per_share": round(pnl_per_share, 2),
        "total_pnl": total_pnl,
        "roi_pct": roi_pct,
        "verdict": "PROFIT" if total_pnl >= 0 else "LOSS"
    }
