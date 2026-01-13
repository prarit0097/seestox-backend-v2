# core_engine/data_fetch.py

import time
import threading
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

import yfinance as yf

# ---------------- CACHE ---------------- #
_CACHE = {}
_CACHE_LOCK = threading.Lock()

# remembers which Yahoo base symbol worked for a given canonical symbol
_YF_SUCCESS_MAP = {}
_YF_SUCCESS_LOCK = threading.Lock()

MARKET_OPEN_TTL = 30        # 30 sec
MARKET_CLOSED_TTL = 1800    # 30 min

IST = ZoneInfo("Asia/Kolkata")


# ---------------- MARKET CLOCK ---------------- #
def is_market_open():
    # IMPORTANT: droplet usually runs UTC; use IST explicitly
    now = datetime.now(IST).time()
    return dtime(9, 15) <= now <= dtime(15, 30)


def _is_cache_valid(ts, ttl):
    return (time.time() - ts) < ttl


def _parse_symbol(symbol: str):
    """
    Returns: (base_symbol, suffix)
    base_symbol: 'TATAMOTORS'
    suffix: '.NS' or '.BO'
    """
    if not symbol:
        return "", ".NS"

    s = str(symbol).strip().upper()

    suffix = ".NS"
    if s.startswith("NSE:"):
        s = s[4:]
        suffix = ".NS"
    elif s.startswith("BSE:"):
        s = s[4:]
        suffix = ".BO"

    if s.endswith(".NS"):
        s = s[:-3]
        suffix = ".NS"
    elif s.endswith(".BO"):
        s = s[:-3]
        suffix = ".BO"

    return s.strip(), suffix


# Known fallback candidates for symbols that often change on Yahoo after rename/demerger.
# We try these ONLY if the normal BASE.NS fails.
_YF_OVERRIDES = {
    # Tata Motors CV demerger tickers vary across sources/feeds; try a few common ones.
    "TATAMOTORS": ["TMCV", "TMCVL", "TMLCV"],
    # Zomato rebrand to Eternal is often referenced as ETEA on some feeds.
    "ZOMATO": ["ETEA", "ETERNAL"],
}


def fetch_stock_data(symbol: str, period="6mo"):
    base_symbol, suffix = _parse_symbol(symbol)
    if not base_symbol:
        raise ValueError("Empty symbol")

    ttl = MARKET_OPEN_TTL if is_market_open() else MARKET_CLOSED_TTL

    # Build candidate Yahoo symbols
    candidates = []

    # If we already discovered a working yahoo base for this symbol, try it first
    with _YF_SUCCESS_LOCK:
        known = _YF_SUCCESS_MAP.get(base_symbol)

    if known:
        candidates.append(f"{known}{suffix}")

    # Normal expected yahoo symbol
    candidates.append(f"{base_symbol}{suffix}")

    # Overrides (only if needed)
    for alt in _YF_OVERRIDES.get(base_symbol, []):
        candidates.append(f"{alt}{suffix}")

    # de-dup while preserving order
    seen = set()
    candidates = [c for c in candidates if not (c in seen or seen.add(c))]

    last_err = None
    df = None
    used_yf_symbol = None

    for yf_symbol in candidates:
        cache_key = (base_symbol, yf_symbol, period)

        # -------- HISTORICAL CACHE -------- #
        with _CACHE_LOCK:
            if cache_key in _CACHE:
                ts, cached_df = _CACHE[cache_key]
                if _is_cache_valid(ts, ttl):
                    print(f"⚡ Cache HIT ({'OPEN' if is_market_open() else 'CLOSED'}): {base_symbol} via {yf_symbol}")
                    df = cached_df.copy()
                    used_yf_symbol = yf_symbol
                    break
                else:
                    del _CACHE[cache_key]

        # -------- FETCH FROM YAHOO -------- #
        if df is None:
            try:
                print(f"🌐 Fetching historical data: {base_symbol} via {yf_symbol}")
                tmp = yf.download(
                    yf_symbol,
                    period=period,
                    progress=False,
                    threads=False
                )
                if tmp is None or tmp.empty:
                    last_err = f"No data for {yf_symbol}"
                    continue

                tmp = tmp.reset_index()
                df = tmp
                used_yf_symbol = yf_symbol

                with _CACHE_LOCK:
                    _CACHE[cache_key] = (time.time(), df.copy())

                # remember the working mapping (base -> yahoo base without suffix)
                with _YF_SUCCESS_LOCK:
                    _YF_SUCCESS_MAP[base_symbol] = yf_symbol.replace(suffix, "")
                break

            except Exception as e:
                last_err = str(e)
                continue

    if df is None:
        raise ValueError(f"No historical data for {base_symbol}. Last error: {last_err}")

    # -------- LIVE PRICE PATCH -------- #
    if is_market_open() and used_yf_symbol:
        try:
            ticker = yf.Ticker(used_yf_symbol)
            live_price = None
            try:
                live_price = ticker.fast_info.get("last_price")
            except Exception:
                live_price = None

            if live_price:
                df.loc[df.index[-1], "Close"] = float(live_price)
        except Exception:
            pass  # never crash

    # IMPORTANT: keep canonical symbol in df
    df["symbol"] = base_symbol
    # optional debug
    df.attrs["yf_symbol"] = used_yf_symbol

    return df

