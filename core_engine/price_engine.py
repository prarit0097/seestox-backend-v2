# core_engine/price_engine.py
# =====================================
# HYBRID PRICE ENGINE (REAL + CACHE)
# =====================================

import time
import threading
import yfinance as yf

PRICE_CACHE = {}
CHANGE_CACHE = {}
LAST_FETCH = {}

FETCH_INTERVAL = 3  # seconds (Yahoo API hit)
LOCK = threading.Lock()


def _fetch_quote_from_yahoo(symbol: str):
    try:
        ticker = yf.Ticker(symbol + ".NS")
        data = ticker.history(period="2d")

        if data.empty:
            return None, None

        close = float(data["Close"].iloc[-1])
        prev = float(data["Close"].iloc[-2]) if len(data["Close"]) > 1 else None
        change_pct = None
        if prev and prev != 0:
            change_pct = round(((close - prev) / prev) * 100, 2)

        return round(close, 2), change_pct

    except Exception:
        return None, None


def get_price(symbol: str):
    """
    FAST READ:
    - JS calls every 3 sec
    - This function NEVER calls Yahoo directly
    """

    with LOCK:
        return PRICE_CACHE.get(symbol)


def get_change_percent(symbol: str):
    with LOCK:
        return CHANGE_CACHE.get(symbol)


def _price_updater():
    """
    BACKGROUND THREAD
    - Updates PRICE_CACHE every 60 seconds
    """
    while True:
        try:
            with LOCK:
                symbols = list(PRICE_CACHE.keys())

            updates = {}
            for symbol in symbols:
                price, change_pct = _fetch_quote_from_yahoo(symbol)
                if price:
                    updates[symbol] = (price, change_pct)

            if updates:
                with LOCK:
                    for symbol, quote in updates.items():
                        price, change_pct = quote
                        PRICE_CACHE[symbol] = price
                        CHANGE_CACHE[symbol] = change_pct
                        LAST_FETCH[symbol] = time.time()

        except Exception:
            pass

        time.sleep(FETCH_INTERVAL)


def register_symbol(symbol: str):
    """
    Call this ONCE when stock is added
    """
    with LOCK:
        if symbol in PRICE_CACHE:
            return

    price, change_pct = _fetch_quote_from_yahoo(symbol)
    with LOCK:
        if symbol not in PRICE_CACHE:
            PRICE_CACHE[symbol] = price
            CHANGE_CACHE[symbol] = change_pct
            LAST_FETCH[symbol] = time.time()


# =====================================
# START BACKGROUND UPDATER (ON IMPORT)
# =====================================
threading.Thread(target=_price_updater, daemon=True).start()
