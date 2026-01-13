# core_engine/symbol_resolver.py

import os
import pandas as pd
import re   # ✅ REQUIRED (MANDATORY ADD)

# =====================================================
# PATH RESOLUTION
# =====================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SYMBOL_DIR = os.path.join(BASE_DIR, "symbol_master")

CSV_CANDIDATES = [
    "equity_master.csv",
    "nse_master.csv",
]

MASTER_PATH = None
for name in CSV_CANDIDATES:
    path = os.path.join(SYMBOL_DIR, name)
    if os.path.exists(path):
        MASTER_PATH = path
        break

if not MASTER_PATH:
    raise RuntimeError(
        "❌ No symbol master CSV found. "
        "Expected equity_master.csv or nse_master.csv"
    )

# =====================================================
# LOAD CSV
# =====================================================

try:
    DF = pd.read_csv(MASTER_PATH)
except Exception as e:
    raise RuntimeError(f"❌ Failed to load symbol master CSV: {e}")

# Normalize column names
DF.columns = [c.lower().strip() for c in DF.columns]

# =====================================================
# AUTO-DETECT COMPANY COLUMN
# =====================================================

COMPANY_COL_CANDIDATES = [
    "company",
    "company_name",
    "name",
    "security_name",
    "issuer_name",
]

COMPANY_COL = None
for col in COMPANY_COL_CANDIDATES:
    if col in DF.columns:
        COMPANY_COL = col
        break

if not COMPANY_COL:
    raise RuntimeError(
        f"❌ No company column found. "
        f"Available columns: {list(DF.columns)}"
    )

# =====================================================
# NORMALIZE REQUIRED COLUMNS
# =====================================================

if "symbol" not in DF.columns:
    raise RuntimeError("❌ 'symbol' column missing in CSV")

DF["symbol"] = DF["symbol"].astype(str).str.upper().str.strip()
DF["company"] = DF[COMPANY_COL].astype(str).str.upper().str.strip()

if "exchange" in DF.columns:
    DF["exchange"] = DF["exchange"].astype(str).str.upper().str.strip()
else:
    DF["exchange"] = "NSE"

# Common aliases for user-friendly tickers.
_SYMBOL_ALIASES = {
    "RIL": "RELIANCE",
}

# =====================================================
# 🔍 CHAT-SAFE ANALYZE FLOW (ONLY FIXED PART)
# ==================================================
def resolve_symbol(user_input: str):
    """
    CHAT SAFE:
    - Sentence se symbol extract kare
    - Exception kabhi throw na kare
    - IMPORTANT: explicit tickers (.NS/.BO or NSE:/BSE:) pe fuzzy match NEVER
    """

    if not user_input or not user_input.strip():
        return None

    text = user_input.strip().upper()

    # Detect explicit ticker style input (single token)
    # Examples: TATAMOTORS.NS, ZOMATO.NS, NSE:TCS, BSE:RELIANCE, TATAMOTORS
    is_explicit = bool(
        re.fullmatch(r"[A-Z0-9&\-\.\:]{1,25}", text) and (" " not in text)
    )

    raw = text
    for prefix in ("NSE:", "BSE:"):
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
            break

    # Strip suffix for matching in master
    raw_stripped = raw
    for suffix in (".NS", ".BO"):
        if raw_stripped.endswith(suffix):
            raw_stripped = raw_stripped[: -len(suffix)]
            break
    raw_stripped = raw_stripped.strip()

    # Alias direct
    alias = _SYMBOL_ALIASES.get(raw_stripped)
    if alias:
        exact = DF[DF["symbol"] == alias]
        if not exact.empty:
            row = exact.iloc[0]
            return row["symbol"], row["company"]

    # Exact symbol match (stripped)
    exact = DF[DF["symbol"] == raw_stripped]
    if not exact.empty:
        row = exact.iloc[0]
        return row["symbol"], row["company"]

    # ✅ If explicit ticker provided and not found in master:
    # DO NOT fuzzy match (prevents NS -> MICRO**NS** bug)
    # return safe fallback (base symbol)
    if is_explicit:
        return raw_stripped, raw_stripped

    # Otherwise: sentence parsing + fuzzy matching
    tokens = re.findall(r"\b[A-Z]{2,10}\b", text)

    # Remove noisy tokens
    stop = {"NSE", "BSE", "NS", "BO", "LTD", "LIMITED"}
    tokens = [t for t in tokens if t not in stop and len(t) >= 3]

    # Alias resolution in sentence
    for token in tokens:
        alias = _SYMBOL_ALIASES.get(token)
        if alias:
            exact = DF[DF["symbol"] == alias]
            if not exact.empty:
                row = exact.iloc[0]
                return row["symbol"], row["company"]

    # 1️⃣ Exact symbol match
    for token in tokens:
        exact = DF[DF["symbol"] == token]
        if not exact.empty:
            row = exact.iloc[0]
            return row["symbol"], row["company"]

    # 2️⃣ Company startswith
    for token in tokens:
        starts = DF[DF["company"].str.startswith(token)]
        if not starts.empty:
            row = starts.iloc[0]
            return row["symbol"], row["company"]

    # 3️⃣ Company contains
    for token in tokens:
        contains = DF[DF["company"].str.contains(token, na=False)]
        if not contains.empty:
            row = contains.iloc[0]
            return row["symbol"], row["company"]

    # 4️⃣ Symbol contains
    for token in tokens:
        sym_contains = DF[DF["symbol"].str.contains(token, na=False)]
        if not sym_contains.empty:
            row = sym_contains.iloc[0]
            return row["symbol"], row["company"]

    return None


# =====================================================
# 🔎 AUTOCOMPLETE FLOW (UNCHANGED)
# =====================================================

def search_companies(query: str, limit: int = 10):
    if not query or not query.strip():
        return []

    q = query.strip().upper()
    results = []

    alias = _SYMBOL_ALIASES.get(q)
    if alias:
        alias_row = DF[DF["symbol"] == alias]
        if not alias_row.empty:
            row = alias_row.iloc[0]
            results.append({
                "symbol": row["symbol"],
                "company": row["company"],
                "exchange": row.get("exchange", "NSE")
            })

    df = DF[
        (DF["symbol"].str.contains(q, na=False)) |
        (DF["company"].str.contains(q, na=False))
    ]

    if df.empty:
        return results

    remaining = max(0, limit - len(results))
    if remaining == 0:
        return results

    for _, row in df.head(remaining).iterrows():
        if results and row["symbol"] == results[0]["symbol"]:
            continue
        results.append({
            "symbol": row["symbol"],
            "company": row["company"],
            "exchange": row.get("exchange", "NSE")
        })

    return results
