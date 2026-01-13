import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SYMBOL_MASTER = os.path.join(BASE_DIR, "symbol_master", "nse_master.csv")


def _load_master_symbols(limit):
    symbols = []
    try:
        with open(SYMBOL_MASTER, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                sym = line.split(",", 1)[0].strip()
                if sym.lower() == "symbol":
                    continue
                symbols.append(sym)
                if len(symbols) >= limit:
                    break
    except Exception:
        return []
    return symbols


_BASE_STOCKS = [
    # NIFTY 50 (Core)
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
    "SBIN", "ITC", "LT", "AXISBANK", "HINDUNILVR",
    "WIPRO", "HCLTECH", "KOTAKBANK", "BHARTIARTL",
    "BAJFINANCE", "ASIANPAINT", "MARUTI", "SUNPHARMA",
    "ULTRACEMCO", "NTPC", "POWERGRID", "TITAN",
    "ADANIENT", "ADANIPORTS", "ONGC", "COALINDIA",
    "JSWSTEEL", "TATASTEEL", "INDUSINDBK", "NESTLEIND",
    "BAJAJFINSV", "BPCL", "HDFCLIFE", "SBILIFE",
    "DIVISLAB", "CIPLA", "GRASIM", "TECHM",
    "DRREDDY", "EICHERMOT", "HEROMOTOCO", "BRITANNIA",
    "APOLLOHOSP", "TMCV", "UPL", "SHRIRAMFIN",
    "M&M", "HINDALCO",

    # Large / Strong Mid Caps (Market Leaders)
    "DMART", "PIDILITIND", "AMBUJACEM", "ACC",
    "SIEMENS", "ABB", "DLF", "LODHA",
    "ICICIPRULI", "HAVELLS", "GODREJCP",
    "TATACONSUM", "MARICO", "DABUR",
    "ICICIGI", "CHOLAFIN", "BAJAJHLDNG",
    "INDIGO", "ETERNAL", "PAYTM",
    "POLYCAB", "AUBANK", "TORNTPHARM",
    "LUPIN", "ALKEM", "BANDHANBNK"
]

_all_symbols = []
_seen = set()
for _sym in _BASE_STOCKS + _load_master_symbols(100):
    if _sym not in _seen:
        _seen.add(_sym)
        _all_symbols.append(_sym)

# Keep the name for existing imports, but expand to 100 symbols.
TOP_100_STOCKS = _all_symbols[:100]
