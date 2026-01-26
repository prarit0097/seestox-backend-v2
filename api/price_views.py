# api/price_views.py
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET
import yfinance as yf
from datetime import datetime, timezone
import math
import json
import os
import re
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

from api.models import Watchlist
from core_engine.analyzer import analyze_stock
from core_engine.price_engine import (
    PRICE_CACHE,
    get_price,
    get_change_percent,
    register_symbol,
)
from core_engine.symbol_resolver import resolve_symbol, DF
from core_engine.news_fetcher import get_market_news

_SYMBOL_ALIASES = {
    "RIL": "RELIANCE",
}

_COMMON_WORDS = {
    "LTD",
    "LIMITED",
    "BANK",
    "INDIA",
    "THE",
    "CO",
    "COMPANY",
    "SERVICES",
    "HOLDINGS",
    "FINANCIAL",
    "FINANCE",
    "CORP",
    "CORPORATION",
    "INDUSTRIES",
}

_PEERS_MAP_CACHE = None
_PEER_UNIVERSE_CACHE = None
_TICKER_INFO_CACHE = {}
_TICKER_INFO_MAX = 200


def _config_path(filename: str) -> str:
    base = os.path.dirname(os.path.dirname(__file__))
    return os.path.join(base, "config", filename)


def _load_json_file(filename, default):
    path = _config_path(filename)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return default


def _peers_map():
    global _PEERS_MAP_CACHE
    if _PEERS_MAP_CACHE is None:
        _PEERS_MAP_CACHE = _load_json_file("peers_map.json", {})
    return _PEERS_MAP_CACHE


def _peer_universe():
    global _PEER_UNIVERSE_CACHE
    if _PEER_UNIVERSE_CACHE is None:
        _PEER_UNIVERSE_CACHE = _load_json_file("peer_universe.json", [])
    return _PEER_UNIVERSE_CACHE


def _normalize_peer_symbol(symbol: str) -> str:
    if symbol.endswith(".NS") or symbol.endswith(".BO"):
        return symbol
    return f"{symbol}.NS"


def _strip_suffix(symbol: str) -> str:
    return symbol.replace(".NS", "").replace(".BO", "")


def _get_ticker_info(symbol: str):
    if symbol in _TICKER_INFO_CACHE:
        return _TICKER_INFO_CACHE[symbol]
    try:
        info = yf.Ticker(symbol).info or {}
    except Exception:
        info = {}
    if len(_TICKER_INFO_CACHE) >= _TICKER_INFO_MAX:
        _TICKER_INFO_CACHE.clear()
    _TICKER_INFO_CACHE[symbol] = info
    return info


def _extract_keywords(text: str):
    if not text:
        return set()
    tokens = []
    for token in text.upper().replace(",", " ").split():
        token = token.strip()
        if token and token not in _COMMON_WORDS and len(token) > 3:
            tokens.append(token)
    return set(tokens)


def _as_percent(value):
    if value is None:
        return None
    try:
        number = float(value)
    except Exception:
        return None
    if not math.isfinite(number):
        return None
    if abs(number) <= 1:
        number = number * 100
    return round(number, 2)


def _parse_major_holders(major):
    data = {}
    if major is None:
        return data
    try:
        if hasattr(major, "iterrows"):
            for idx, row in major.iterrows():
                label = str(idx)
                value = None
                try:
                    value = row.iloc[0]
                except Exception:
                    pass
                data[label] = value
    except Exception:
        return data
    return data


def _holder_percent(major_map, info, key_candidates, info_key):
    value = _as_percent(info.get(info_key)) if info else None
    if value is not None:
        return value
    for label, raw_value in major_map.items():
        label_upper = label.upper()
        if not any(candidate in label_upper for candidate in key_candidates):
            continue
        match = re.search(r"([0-9.]+)\s*%", label)
        if match:
            return _as_percent(match.group(1))
        value = _as_percent(raw_value)
        if value is not None:
            return value
    return None


def _shareholding_data(ticker):
    data = {
        "promoters": [],
        "fii": [],
        "dii": [],
        "public": [],
        "other": [],
    }
    if ticker is None:
        return data, "none", "Shareholding data unavailable for this symbol."
    try:
        info = ticker.info or {}
        major = _parse_major_holders(getattr(ticker, "major_holders", None))
    except Exception:
        info = {}
        major = {}

    promoters = _holder_percent(major, info, ["INSIDER"], "heldPercentInsiders")
    institutions = _holder_percent(major, info, ["INSTITUTION"], "heldPercentInstitutions")
    public = None
    if promoters is not None and institutions is not None:
        remainder = round(100 - (promoters + institutions), 2)
        if remainder >= 0 and remainder <= 100:
            public = remainder

    def _series(value):
        if value is None:
            return []
        return [{"label": "Latest", "value": value}]

    data["promoters"] = _series(promoters)
    data["fii"] = _series(institutions)
    data["public"] = _series(public)

    mode = "auto" if any(data.values()) else "none"
    note = (
        "Shareholding is best-effort from public data. FII/DII may be combined."
        if mode == "auto"
        else "Shareholding data unavailable for this symbol."
    )
    return data, mode, note


def _peer_score(base_info, peer_info):
    score = 0.0
    base_sector = (base_info.get("sector") or "").strip().lower()
    base_industry = (base_info.get("industry") or "").strip().lower()
    peer_sector = (peer_info.get("sector") or "").strip().lower()
    peer_industry = (peer_info.get("industry") or "").strip().lower()

    if base_industry and peer_industry and base_industry == peer_industry:
        score += 6
    if base_sector and peer_sector and base_sector == peer_sector:
        score += 3

    base_cap = base_info.get("marketCap")
    peer_cap = peer_info.get("marketCap")
    try:
        base_cap = float(base_cap) if base_cap is not None else None
        peer_cap = float(peer_cap) if peer_cap is not None else None
    except Exception:
        base_cap = None
        peer_cap = None
    if base_cap and peer_cap and base_cap > 0 and peer_cap > 0:
        ratio = peer_cap / base_cap
        if 0.7 <= ratio <= 1.3:
            score += 2
        elif 0.5 <= ratio <= 2.0:
            score += 1

    for key, weight in [("trailingPE", 0.4), ("priceToBook", 0.3)]:
        base_val = base_info.get(key)
        peer_val = peer_info.get(key)
        try:
            base_val = float(base_val) if base_val is not None else None
            peer_val = float(peer_val) if peer_val is not None else None
        except Exception:
            base_val = None
            peer_val = None
        if base_val and peer_val and base_val > 0 and peer_val > 0:
            diff = abs(peer_val - base_val) / base_val
            score += max(0.0, 1.0 - diff) * weight

    return score


def _auto_peers(symbol: str, max_peers: int = 5):
    base_symbol = _normalize_peer_symbol(symbol)
    base_info = _get_ticker_info(base_symbol)
    base_sector = base_info.get("sector")
    base_industry = base_info.get("industry")
    base_cap = base_info.get("marketCap")
    base_summary = base_info.get("longBusinessSummary") or ""

    if not base_sector and not base_industry and not base_cap:
        return []

    universe = _peer_universe()
    if not universe:
        return []

    base_keywords = _extract_keywords(base_summary)
    candidates = []
    for peer_symbol in universe:
        if peer_symbol == base_symbol:
            continue
        peer_info = _get_ticker_info(peer_symbol)
        peer_sector = peer_info.get("sector")
        peer_industry = peer_info.get("industry")
        if base_sector and peer_sector and base_sector != peer_sector:
            continue
        if base_industry and peer_industry and base_industry != peer_industry:
            continue
        if not base_industry and not base_sector and base_keywords:
            peer_summary = peer_info.get("longBusinessSummary") or ""
            if not _extract_keywords(peer_summary).intersection(base_keywords):
                continue
        candidates.append((peer_symbol, peer_info))

    scored = []
    for peer_symbol, peer_info in candidates:
        score = _peer_score(base_info, peer_info)
        if score == 0:
            continue
        scored.append((score, peer_symbol))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [symbol for _, symbol in scored[:max_peers]]


def _build_peer_rows(symbol: str, company: str, max_peers: int = 5):
    peers_mode = "none"
    note = "Peers unavailable for this symbol."
    peers_list = []

    manual_map = _peers_map()
    manual_key = _normalize_peer_symbol(symbol)
    manual_peers = manual_map.get(manual_key)
    if manual_peers:
        peers_mode = "manual"
        note = ""
        peers_list = manual_peers[:max_peers]
    else:
        auto_peers = _auto_peers(symbol, max_peers=max_peers)
        if auto_peers:
            peers_mode = "auto"
            note = "Peers are indicative (best-effort) based on available public data."
            peers_list = auto_peers

    peers = []
    for peer_symbol in peers_list:
        peer_symbol = _normalize_peer_symbol(peer_symbol)
        info = _get_ticker_info(peer_symbol)
        base_symbol = _strip_suffix(peer_symbol)
        register_symbol(base_symbol)
        price = get_price(base_symbol)
        change_pct = get_change_percent(base_symbol)
        if not info and price is None and change_pct is None:
            continue
        market_cap = info.get("marketCap")
        pe = info.get("trailingPE")
        pb = info.get("priceToBook")
        div_yield = info.get("dividendYield")
        try:
            div_yield = float(div_yield) * 100 if div_yield is not None else None
        except Exception:
            div_yield = None

        name = (
            info.get("shortName")
            or info.get("longName")
            or _company_for_symbol(base_symbol)
            or base_symbol
        )
        peers.append({
            "symbol": base_symbol,
            "company": name,
            "current_price": price,
            "change_percent": change_pct,
            "market_cap": market_cap,
            "pe": pe,
            "pb": pb,
            "dividend_yield": div_yield,
        })

    return peers, peers_mode, note


@login_required
def watchlist_price_data(request):
    items = Watchlist.objects.filter(user=request.user)

    data = []
    for item in items:
        symbol = item.symbol
        price = PRICE_CACHE.get(symbol)

        data.append({
            "symbol": symbol,
            "current_price": price
        })

    return JsonResponse({"watchlist": data})


@require_GET
def quotes_api(request):
    symbols = request.GET.get("symbols", "")
    symbols = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    data = []
    for symbol in symbols:
        resolved = _SYMBOL_ALIASES.get(symbol, symbol)
        register_symbol(resolved)
        data.append({
            "symbol": symbol,
            "current_price": get_price(resolved),
            "change_percent": get_change_percent(resolved),
        })
    return JsonResponse({"quotes": data})


def _exchange_for_symbol(symbol: str) -> str:
    try:
        row = DF[DF["symbol"] == symbol]
        if not row.empty:
            value = str(row.iloc[0].get("exchange") or "NSE").strip()
            return value or "NSE"
    except Exception:
        pass
    return "NSE"


def _company_for_symbol(symbol: str) -> str:
    try:
        row = DF[DF["symbol"] == symbol]
        if not row.empty:
            return str(row.iloc[0].get("company") or symbol).strip()
    except Exception:
        pass
    return symbol


def _peer_symbols(company: str, symbol: str, limit: int = 4):
    if not company:
        return []
    tokens = [
        token
        for token in company.upper().split()
        if token and token not in _COMMON_WORDS and len(token) > 2
    ]
    if not tokens:
        return []
    try:
        pattern = "|".join(tokens)
        rows = DF[DF["company"].str.contains(pattern, na=False)]
    except Exception:
        return []
    scored = []
    token_set = set(tokens)
    for _, row in rows.iterrows():
        sym = row["symbol"]
        if sym == symbol:
            continue
        name = str(row.get("company") or "")
        name_tokens = set(name.upper().split())
        score = len(token_set.intersection(name_tokens))
        if score == 0:
            continue
        scored.append((score, sym))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [sym for _, sym in scored[:limit]]


def _to_epoch(iso_string: str):
    if not iso_string:
        return None
    try:
        normalized = iso_string.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        return int(dt.replace(tzinfo=timezone.utc).timestamp())
    except Exception:
        return None


def _format_compact(value):
    try:
        number = float(value)
    except Exception:
        return None
    if not math.isfinite(number):
        return None
    abs_val = abs(number)
    if abs_val >= 1_000_000_000_000:
        return f"{number / 1_000_000_000_000:.2f}T"
    if abs_val >= 1_000_000_000:
        return f"{number / 1_000_000_000:.2f}B"
    if abs_val >= 1_000_000:
        return f"{number / 1_000_000:.2f}M"
    if abs_val >= 1_000:
        return f"{number / 1_000:.2f}K"
    return f"{number:.2f}"


def _intraday_chart(symbol: str):
    ticker = yf.Ticker(f"{symbol}.NS")
    candidates = [
        ("1d", "5m", "%H:%M"),
        ("5d", "15m", "%d %b %H:%M"),
        ("1mo", "1d", "%d %b"),
    ]
    for period, interval, label_fmt in candidates:
        try:
            data = ticker.history(period=period, interval=interval)
        except Exception:
            data = None
        if data is None or data.empty:
            continue
        points = []
        for index, row in data.iterrows():
            try:
                price = float(row.get("Close", 0))
            except Exception:
                continue
            if price == 0 or not math.isfinite(price):
                continue
            ts_val = None
            try:
                ts_val = int(index.timestamp())
            except Exception:
                ts_val = None
            points.append({
                "t": index.strftime(label_fmt),
                "p": round(price, 2),
                "time": index.strftime(label_fmt),
                "price": round(price, 2),
                "ts": ts_val,
            })
        if not points:
            continue
        low = float(data["Low"].min()) if "Low" in data else None
        high = float(data["High"].max()) if "High" in data else None
        if low is not None and not math.isfinite(low):
            low = None
        if high is not None and not math.isfinite(high):
            high = None
        first = points[0]["p"]
        last = points[-1]["p"]
        day_return = None
        if first:
            value = ((last - first) / first) * 100
            if math.isfinite(value):
                day_return = round(value, 2)
        low_out = round(low, 2) if low is not None else None
        high_out = round(high, 2) if high is not None else None
        return points, low_out, high_out, day_return
    return [], None, None, None


def _build_financials(info: dict):
    def _guardrail(metric_key, value, market_cap=None):
        if value is None:
            return None, None
        try:
            val = float(value)
        except Exception:
            return None, None
        if not math.isfinite(val):
            return None, None

        def to_fraction(v):
            return v / 100 if abs(v) > 1 else v

        note = None
        if metric_key == "dividend_yield":
            fraction = to_fraction(val)
            large_cap = market_cap is not None and market_cap >= 2_000_000_000_000
            limit = 0.12 if large_cap else 0.20
            if fraction > limit:
                return None, "Dividend yield outlier"
        elif metric_key == "pe":
            if val <= 0 or val > 200:
                return None, "P/E outlier"
        elif metric_key == "pb":
            if val <= 0 or val > 50:
                return None, "P/B outlier"
        elif metric_key == "profit_margin":
            fraction = to_fraction(val)
            if fraction < -1 or fraction > 1:
                return None, "Profit margin outlier"
        elif metric_key in {"roe", "roa"}:
            fraction = to_fraction(val)
            if fraction < -1 or fraction > 1:
                return None, "Return ratio outlier"
        elif metric_key in {"revenue_growth", "earnings_growth"}:
            fraction = to_fraction(val)
            if fraction < -1 or fraction > 5:
                return None, "Growth outlier"
        return val, note

    def add(label, value, percent=False, compact=False, metric_key=None):
        if value is None:
            return
        if metric_key is not None:
            value, _ = _guardrail(metric_key, value, market_cap=info.get("marketCap"))
            if value is None:
                items.append({"label": label, "value": "N/A"})
                return
        if percent:
            try:
                value = float(value) * 100
            except Exception:
                return
            formatted = f"{value:.2f}%"
        elif compact:
            formatted = _format_compact(value)
            if formatted is None:
                return
        else:
            try:
                formatted = f"{float(value):.2f}"
            except Exception:
                formatted = str(value)
        items.append({"label": label, "value": formatted})

    items = []
    add("Market Cap", info.get("marketCap"), compact=True)
    add("P/E (TTM)", info.get("trailingPE"), metric_key="pe")
    add("P/E (Forward)", info.get("forwardPE"), metric_key="pe")
    add("Price to Book", info.get("priceToBook"), metric_key="pb")
    add("Profit Margin", info.get("profitMargins"), percent=True, metric_key="profit_margin")
    add("Return on Equity", info.get("returnOnEquity"), percent=True, metric_key="roe")
    add("Revenue Growth", info.get("revenueGrowth"), percent=True, metric_key="revenue_growth")
    add("Earnings Growth", info.get("earningsGrowth"), percent=True, metric_key="earnings_growth")
    add("Dividend Yield", info.get("dividendYield"), percent=True, metric_key="dividend_yield")
    add("EPS", info.get("trailingEps"))
    add("Beta", info.get("beta"))
    return items


def _latest_value_from_row(row):
    if row is None:
        return None
    try:
        keys = list(row.index)
    except Exception:
        return None
    if not keys:
        return None
    try:
        keys = sorted(keys, reverse=True)
    except Exception:
        pass
    for key in keys:
        try:
            value = float(row[key])
        except Exception:
            continue
        if not math.isfinite(value):
            continue
        return value
    return None


def _latest_value_from_df(df, candidates):
    row = _find_row(df, candidates)
    return _latest_value_from_row(row)


def _cagr_from_row(row, years):
    if row is None:
        return None
    try:
        keys = sorted(list(row.index), reverse=True)
    except Exception:
        keys = list(row.index)
    values = []
    for key in keys:
        try:
            value = float(row[key])
        except Exception:
            continue
        if not math.isfinite(value):
            continue
        values.append(value)
    if len(values) <= years:
        return None
    latest = values[0]
    past = values[years]
    if latest <= 0 or past <= 0:
        return None
    try:
        return (latest / past) ** (1 / years) - 1
    except Exception:
        return None


def _to_percent(value):
    if value is None:
        return None
    try:
        val = float(value)
    except Exception:
        return None
    if not math.isfinite(val):
        return None
    if abs(val) <= 1:
        val = val * 100
    return round(val, 2)


def _guardrail_numeric(metric_key, value, market_cap=None):
    if value is None:
        return None, None
    try:
        val = float(value)
    except Exception:
        return None, None
    if not math.isfinite(val):
        return None, None

    def to_fraction(v):
        return v / 100 if abs(v) > 1 else v

    note = None
    if metric_key == "dividend_yield":
        fraction = to_fraction(val)
        large_cap = market_cap is not None and market_cap >= 2_000_000_000_000
        limit = 0.12 if large_cap else 0.20
        if fraction > limit:
            return None, "Dividend yield outlier"
    elif metric_key == "pe":
        if val <= 0 or val > 200:
            return None, "P/E outlier"
    elif metric_key == "pb":
        if val <= 0 or val > 50:
            return None, "P/B outlier"
    elif metric_key == "debt_to_equity":
        if val <= 0 or val > 10:
            return None, "Debt/Equity outlier"
    elif metric_key in {"profit_margin", "roe", "roa", "roce"}:
        fraction = to_fraction(val)
        if fraction < -1 or fraction > 1:
            return None, "Margin outlier"
    elif metric_key in {"revenue_growth", "earnings_growth", "revenue_cagr", "profit_cagr"}:
        fraction = to_fraction(val)
        if fraction < -1 or fraction > 5:
            return None, "Growth outlier"
    elif metric_key == "payout_ratio":
        fraction = to_fraction(val)
        if fraction < 0 or fraction > 1.5:
            return None, "Payout ratio outlier"
    return val, note


def _metric(value, unit, label, key, market_cap=None, note_override=None):
    value, note = _guardrail_numeric(key, value, market_cap=market_cap)
    if note_override:
        note = note_override
        if value is None:
            return {"value": None, "unit": unit, "label": label, "note": note}
    return {"value": value, "unit": unit, "label": label, "note": note}


def _financial_quality(metrics):
    total = 0
    missing = 0
    outliers = []
    key_metric_keys = {
        "debt_to_equity",
        "current_ratio",
        "free_cashflow",
        "dividend_yield",
        "pe_ttm",
        "price_to_book",
        "roe",
        "roa",
        "roce",
    }
    for section in metrics.values():
        if not isinstance(section, dict):
            continue
        for key, metric in section.items():
            if not isinstance(metric, dict):
                continue
            total += 1
            if metric.get("value") is None:
                missing += 1
            note = metric.get("note")
            if note:
                outliers.append(f"{key}: {note}")
    if outliers and any(entry.split(":")[0] in key_metric_keys for entry in outliers):
        return "OUTLIER", outliers
    if total and missing >= max(8, total // 2):
        return "OUTLIER", []
    if total and missing >= max(3, total // 3):
        return "LIMITED", []
    return "GOOD", []


def _build_structured_financials(info, ticker):
    snapshot = {}
    balance_sheet = {}
    cashflow = {}
    ratios = {}
    market_cap = info.get("marketCap")

    try:
        annual_financials = ticker.financials if ticker else None
        annual_balance = ticker.balance_sheet if ticker else None
        annual_cashflow = ticker.cashflow if ticker else None
    except Exception:
        annual_financials = None
        annual_balance = None
        annual_cashflow = None

    total_debt = info.get("totalDebt")
    if total_debt is None:
        short_debt = _latest_value_from_df(annual_balance, ["Short Long Term Debt", "Short Term Debt"])
        long_debt = _latest_value_from_df(annual_balance, ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"])
        if short_debt is not None or long_debt is not None:
            total_debt = (short_debt or 0) + (long_debt or 0)

    cash = info.get("totalCash")
    if cash is None:
        cash = _latest_value_from_df(
            annual_balance,
            [
                "Cash And Cash Equivalents",
                "Cash Cash Equivalents And Short Term Investments",
                "Cash And Cash Equivalents",
            ],
        )

    equity = _latest_value_from_df(
        annual_balance,
        ["Total Stockholder Equity", "Total Equity Gross Minority Interest"],
    )
    current_assets = _latest_value_from_df(
        annual_balance,
        ["Total Current Assets", "Current Assets"],
    )
    current_liabilities = _latest_value_from_df(
        annual_balance,
        ["Total Current Liabilities", "Current Liabilities"],
    )
    inventory = _latest_value_from_df(annual_balance, ["Inventory"])
    ebit = _latest_value_from_df(annual_financials, ["EBIT", "Operating Income", "EBITDA"])
    interest_expense = _latest_value_from_df(
        annual_financials,
        ["Interest Expense", "Interest Expense And Debt", "Interest Expense Non Operating"],
    )
    if interest_expense is not None and interest_expense < 0:
        interest_expense = abs(interest_expense)

    total_revenue = info.get("totalRevenue")
    if total_revenue is None:
        total_revenue = _latest_value_from_df(
            annual_financials,
            ["Total Revenue", "Operating Revenue", "Total Operating Revenue"],
        )

    operating_cashflow = info.get("operatingCashflow")
    if operating_cashflow is None:
        operating_cashflow = _latest_value_from_df(
            annual_cashflow,
            [
                "Total Cash From Operating Activities",
                "Operating Cash Flow",
                "Net Cash Provided By Operating Activities",
            ],
        )
    capex = _latest_value_from_df(
        annual_cashflow,
        ["Capital Expenditures", "Capital Expenditure"],
    )
    free_cashflow = info.get("freeCashflow")
    fcf_note = None
    if free_cashflow is None and operating_cashflow is not None and capex is not None:
        free_cashflow = operating_cashflow - abs(capex)
    if free_cashflow is not None and operating_cashflow is not None and capex is not None:
        expected = operating_cashflow + capex
        if abs(free_cashflow - expected) > max(1e7, abs(expected) * 0.25):
            free_cashflow = None
            fcf_note = "FCF outlier"

    dividend_rate = info.get("dividendRate")
    if dividend_rate is None:
        dividend_rate = info.get("trailingAnnualDividendRate")

    snapshot.update({
        "market_cap": _metric(market_cap, "Rs", "Market Cap", "market_cap", market_cap=market_cap),
        "pe_ttm": _metric(info.get("trailingPE"), "x", "P/E (TTM)", "pe", market_cap=market_cap),
        "pe_forward": _metric(info.get("forwardPE"), "x", "P/E (Forward)", "pe", market_cap=market_cap),
        "price_to_book": _metric(info.get("priceToBook"), "x", "Price to Book", "pb", market_cap=market_cap),
        "price_to_sales": _metric(info.get("priceToSalesTrailing12Months"), "x", "Price to Sales", "ps", market_cap=market_cap),
        "dividend_yield": _metric(_to_percent(info.get("dividendYield")), "%", "Dividend Yield", "dividend_yield", market_cap=market_cap),
        "dividend_payout": _metric(_to_percent(info.get("payoutRatio")), "%", "Dividend Payout", "payout_ratio", market_cap=market_cap),
        "dividend_per_share": _metric(dividend_rate, "Rs", "Dividend per Share", "dps", market_cap=market_cap),
        "beta": _metric(info.get("beta"), "x", "Beta", "beta", market_cap=market_cap),
    })

    debt_equity_note = None
    debt_equity_value = None
    if equity is None or equity <= 0:
        debt_equity_note = "Insufficient equity data"
    elif total_debt is not None:
        debt_equity_value = total_debt / equity

    balance_sheet.update({
        "total_debt": _metric(total_debt, "Rs", "Total Debt", "total_debt", market_cap=market_cap),
        "cash": _metric(cash, "Rs", "Cash & Equivalents", "cash", market_cap=market_cap),
        "net_debt": _metric(
            (total_debt - cash) if total_debt is not None and cash is not None else None,
            "Rs",
            "Net Debt",
            "net_debt",
            market_cap=market_cap,
        ),
        "debt_to_equity": _metric(
            debt_equity_value,
            "x",
            "Debt/Equity",
            "debt_to_equity",
            market_cap=market_cap,
            note_override=debt_equity_note,
        ),
        "current_ratio": _metric(
            info.get("currentRatio") if info.get("currentRatio") is not None else (
                (current_assets / current_liabilities)
                if current_assets is not None and current_liabilities not in (None, 0)
                else None
            ),
            "x",
            "Current Ratio",
            "current_ratio",
            market_cap=market_cap,
        ),
        "quick_ratio": _metric(
            info.get("quickRatio") if info.get("quickRatio") is not None else (
                ((current_assets - inventory) / current_liabilities)
                if current_assets is not None and inventory is not None and current_liabilities not in (None, 0)
                else None
            ),
            "x",
            "Quick Ratio",
            "quick_ratio",
            market_cap=market_cap,
        ),
        "interest_coverage": _metric(
            (ebit / interest_expense) if ebit is not None and interest_expense not in (None, 0) else None,
            "x",
            "Interest Coverage",
            "interest_coverage",
            market_cap=market_cap,
        ),
        "book_value_per_share": _metric(
            info.get("bookValue") if info.get("bookValue") is not None else (
                (equity / info.get("sharesOutstanding"))
                if equity is not None and info.get("sharesOutstanding")
                else None
            ),
            "Rs",
            "Book Value/Share",
            "book_value",
            market_cap=market_cap,
        ),
    })

    cashflow.update({
        "operating_cashflow": _metric(operating_cashflow, "Rs", "Operating Cash Flow", "cfo", market_cap=market_cap),
        "capex": _metric(capex, "Rs", "Capex", "capex", market_cap=market_cap),
        "free_cashflow": _metric(
            free_cashflow,
            "Rs",
            "Free Cash Flow",
            "fcf",
            market_cap=market_cap,
            note_override=fcf_note,
        ),
        "fcf_margin": _metric(
            _to_percent((free_cashflow / total_revenue) if free_cashflow is not None and total_revenue else None),
            "%",
            "FCF Margin",
            "fcf_margin",
            market_cap=market_cap,
        ),
        "fcf_yield": _metric(
            _to_percent((free_cashflow / market_cap) if free_cashflow is not None and market_cap else None),
            "%",
            "FCF Yield",
            "fcf_yield",
            market_cap=market_cap,
        ),
    })

    ratios.update({
        "roce": _metric(_to_percent(info.get("returnOnCapitalEmployed")), "%", "ROCE", "roce", market_cap=market_cap),
        "roa": _metric(_to_percent(info.get("returnOnAssets")), "%", "ROA", "roa", market_cap=market_cap),
        "roe": _metric(_to_percent(info.get("returnOnEquity")), "%", "ROE", "roe", market_cap=market_cap),
        "ebitda_margin": _metric(_to_percent(info.get("ebitdaMargins")), "%", "EBITDA Margin", "ebitda_margin", market_cap=market_cap),
        "operating_margin": _metric(_to_percent(info.get("operatingMargins")), "%", "Operating Margin", "operating_margin", market_cap=market_cap),
        "profit_margin": _metric(_to_percent(info.get("profitMargins")), "%", "Net Margin", "profit_margin", market_cap=market_cap),
        "revenue_cagr_3y": _metric(_to_percent(_cagr_from_row(_find_row(annual_financials, ["Total Revenue", "Operating Revenue", "Total Operating Revenue"]), 3)), "%", "Revenue CAGR (3Y)", "revenue_cagr", market_cap=market_cap),
        "revenue_cagr_5y": _metric(_to_percent(_cagr_from_row(_find_row(annual_financials, ["Total Revenue", "Operating Revenue", "Total Operating Revenue"]), 5)), "%", "Revenue CAGR (5Y)", "revenue_cagr", market_cap=market_cap),
        "profit_cagr_3y": _metric(_to_percent(_cagr_from_row(_find_row(annual_financials, ["Net Income", "Net Income Common Stockholders", "Net Income Common"]), 3)), "%", "Profit CAGR (3Y)", "profit_cagr", market_cap=market_cap),
        "profit_cagr_5y": _metric(_to_percent(_cagr_from_row(_find_row(annual_financials, ["Net Income", "Net Income Common Stockholders", "Net Income Common"]), 5)), "%", "Profit CAGR (5Y)", "profit_cagr", market_cap=market_cap),
        "ev_to_ebitda": _metric(info.get("enterpriseToEbitda"), "x", "EV/EBITDA", "ev_ebitda", market_cap=market_cap),
        "peg_ratio": _metric(info.get("pegRatio"), "x", "PEG", "peg", market_cap=market_cap),
    })

    quality_status, notes = _financial_quality({
        "snapshot": snapshot,
        "balance_sheet": balance_sheet,
        "cashflow": cashflow,
        "ratios": ratios,
    })
    last_ts = info.get("regularMarketTime")
    last_updated = None
    if last_ts:
        try:
            last_updated = datetime.fromtimestamp(last_ts, tz=timezone.utc).isoformat()
        except Exception:
            last_updated = None

    return {
        "snapshot": snapshot,
        "balance_sheet": balance_sheet,
        "cashflow": cashflow,
        "ratios": ratios,
        "quality": {
            "status": quality_status,
            "notes": notes,
            "source": "Yahoo Finance (best-effort)",
        },
        "last_updated": last_updated,
    }


def _technical_indicators(symbol: str):
    try:
        ticker = yf.Ticker(f"{symbol}.NS")
        data = ticker.history(period="1y")
        if data is None or data.empty:
            return []
        close = data["Close"]
        volume = data["Volume"]
        rsi = None
        try:
            delta = close.diff()
            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)
            avg_gain = gain.rolling(14).mean()
            avg_loss = loss.rolling(14).mean()
            rs = avg_gain / avg_loss.replace(0, 1)
            rsi = 100 - (100 / (1 + rs))
        except Exception:
            rsi = None
        rsi_val = None
        if rsi is not None and not rsi.dropna().empty:
            rsi_val = float(rsi.dropna().iloc[-1])

        dma50 = close.rolling(50).mean()
        dma200 = close.rolling(200).mean()
        dma50_val = None
        if not dma50.dropna().empty:
            dma50_val = float(dma50.dropna().iloc[-1])
        dma200_val = None
        if not dma200.dropna().empty:
            dma200_val = float(dma200.dropna().iloc[-1])

        volume_val = None
        if not volume.dropna().empty:
            volume_val = float(volume.dropna().iloc[-1])

        items = []
        if rsi_val is not None:
            items.append({"label": "14D - RSI", "value": f"{rsi_val:.2f}"})
        if volume_val is not None:
            items.append({"label": "Volume", "value": _format_compact(volume_val)})
        if dma50_val is not None:
            items.append({"label": "50 DMA", "value": f"Rs {dma50_val:.2f}"})
        if dma200_val is not None:
            items.append({"label": "200 DMA", "value": f"Rs {dma200_val:.2f}"})
        return items
    except Exception:
        return []


def _find_row(df, candidates):
    if df is None or getattr(df, "empty", True):
        return None
    try:
        upper_map = {str(idx).upper(): idx for idx in df.index}
        for cand in candidates:
            key = cand.upper()
            if key in upper_map:
                return df.loc[upper_map[key]]
    except Exception:
        return None
    return None


def _series_from_df(df, row, limit=6):
    if row is None:
        return []
    try:
        series = row.dropna()
    except Exception:
        return []
    if series.empty:
        return []
    points = []
    try:
        for col in series.index:
            value = series[col]
            try:
                value = float(value)
            except Exception:
                continue
            if not math.isfinite(value):
                continue
            label = str(col)
            try:
                label = col.strftime("%b '%y")
            except Exception:
                pass
            scaled = value
            if abs(value) >= 1_000_000:
                scaled = value / 1e7
            points.append({
                "label": label,
                "value": round(scaled, 2),
            })
    except Exception:
        return []
    if len(points) > limit:
        points = points[-limit:]
    return points


def _company_financials(ticker):
    data = {
        "net_profit": {"quarterly": [], "annual": []},
        "revenue": {"quarterly": [], "annual": []},
        "balance_sheet": {"quarterly": [], "annual": []},
        "cash_flow": {"quarterly": [], "annual": []},
    }
    if ticker is None:
        return data
    try:
        quarterly_financials = ticker.quarterly_financials
        annual_financials = ticker.financials
        quarterly_balance = ticker.quarterly_balance_sheet
        annual_balance = ticker.balance_sheet
        quarterly_cash = ticker.quarterly_cashflow
        annual_cash = ticker.cashflow
    except Exception:
        return data

    net_profit_row = _find_row(
        quarterly_financials,
        [
            "Net Income",
            "Net Income Common Stockholders",
            "Net Income Common",
            "Net Income Applicable To Common Shares",
        ],
    )
    revenue_row = _find_row(
        quarterly_financials,
        [
            "Total Revenue",
            "Operating Revenue",
            "Total Operating Revenue",
        ],
    )
    data["net_profit"]["quarterly"] = _series_from_df(quarterly_financials, net_profit_row)
    data["revenue"]["quarterly"] = _series_from_df(quarterly_financials, revenue_row)

    net_profit_row_a = _find_row(
        annual_financials,
        [
            "Net Income",
            "Net Income Common Stockholders",
            "Net Income Common",
            "Net Income Applicable To Common Shares",
        ],
    )
    revenue_row_a = _find_row(
        annual_financials,
        [
            "Total Revenue",
            "Operating Revenue",
            "Total Operating Revenue",
        ],
    )
    data["net_profit"]["annual"] = _series_from_df(annual_financials, net_profit_row_a)
    data["revenue"]["annual"] = _series_from_df(annual_financials, revenue_row_a)

    balance_row_q = _find_row(
        quarterly_balance,
        ["Total Assets", "Total Stockholder Equity", "Total Equity Gross Minority Interest"],
    )
    balance_row_a = _find_row(
        annual_balance,
        ["Total Assets", "Total Stockholder Equity", "Total Equity Gross Minority Interest"],
    )
    data["balance_sheet"]["quarterly"] = _series_from_df(quarterly_balance, balance_row_q)
    data["balance_sheet"]["annual"] = _series_from_df(annual_balance, balance_row_a)

    cash_row_q = _find_row(
        quarterly_cash,
        [
            "Total Cash From Operating Activities",
            "Operating Cash Flow",
            "Net Cash Provided By Operating Activities",
        ],
    )
    cash_row_a = _find_row(
        annual_cash,
        [
            "Total Cash From Operating Activities",
            "Operating Cash Flow",
            "Net Cash Provided By Operating Activities",
        ],
    )
    data["cash_flow"]["quarterly"] = _series_from_df(quarterly_cash, cash_row_q)
    data["cash_flow"]["annual"] = _series_from_df(annual_cash, cash_row_a)

    return data


def _format_period_label(value):
    label = str(value)
    try:
        label = value.strftime("%b '%y")
    except Exception:
        pass
    return label


def _ratio_series(
    income_df,
    balance_df,
    numerator_row,
    denominator_row,
    limit=6,
    percent=True,
):
    if income_df is None or getattr(income_df, "empty", True):
        return []
    if balance_df is None or getattr(balance_df, "empty", True):
        return []
    num_series = _find_row(income_df, numerator_row)
    den_series = _find_row(balance_df, denominator_row)
    if num_series is None or den_series is None:
        return []
    points = []
    for col in income_df.columns:
        if col not in balance_df.columns:
            continue
        try:
            num = float(num_series[col])
            den = float(den_series[col])
        except Exception:
            continue
        if not math.isfinite(num) or not math.isfinite(den):
            continue
        if den == 0:
            continue
        value = (num / den) * (100 if percent else 1)
        if not math.isfinite(value):
            continue
        points.append({
            "label": _format_period_label(col),
            "value": round(value, 2),
        })
    if len(points) > limit:
        points = points[-limit:]
    return points


def _eps_series(income_df, limit=6):
    if income_df is None or getattr(income_df, "empty", True):
        return []
    eps_row = _find_row(income_df, ["Basic EPS", "Diluted EPS"])
    if eps_row is None:
        return []
    points = []
    for col in income_df.columns:
        try:
            value = float(eps_row[col])
        except Exception:
            continue
        if not math.isfinite(value):
            continue
        points.append({
            "label": _format_period_label(col),
            "value": round(value, 2),
        })
    if len(points) > limit:
        points = points[-limit:]
    return points


def _roce_series(income_df, balance_df, limit=6):
    if income_df is None or getattr(income_df, "empty", True):
        return []
    if balance_df is None or getattr(balance_df, "empty", True):
        return []
    ebit_row = _find_row(
        income_df,
        ["EBIT", "Operating Income", "EBITDA"],
    )
    assets_row = _find_row(balance_df, ["Total Assets"])
    liabilities_row = _find_row(
        balance_df,
        ["Total Liabilities Net Minority Interest", "Total Liab", "Total Liabilities"],
    )
    if ebit_row is None or assets_row is None:
        return []
    points = []
    for col in income_df.columns:
        if col not in balance_df.columns:
            continue
        try:
            ebit = float(ebit_row[col])
            assets = float(assets_row[col])
            liabilities = float(liabilities_row[col]) if liabilities_row is not None else 0.0
        except Exception:
            continue
        if not (math.isfinite(ebit) and math.isfinite(assets) and math.isfinite(liabilities)):
            continue
        capital_employed = assets - liabilities
        if capital_employed == 0:
            continue
        value = (ebit / capital_employed) * 100
        if not math.isfinite(value):
            continue
        points.append({
            "label": _format_period_label(col),
            "value": round(value, 2),
        })
    if len(points) > limit:
        points = points[-limit:]
    return points


def _dtar_series(balance_df, limit=6):
    if balance_df is None or getattr(balance_df, "empty", True):
        return []
    assets_row = _find_row(balance_df, ["Total Assets"])
    liabilities_row = _find_row(
        balance_df,
        ["Total Liabilities Net Minority Interest", "Total Liab", "Total Liabilities"],
    )
    if assets_row is None or liabilities_row is None:
        return []
    points = []
    for col in balance_df.columns:
        try:
            assets = float(assets_row[col])
            liabilities = float(liabilities_row[col])
        except Exception:
            continue
        if not (math.isfinite(assets) and math.isfinite(liabilities)):
            continue
        if assets == 0:
            continue
        value = (liabilities / assets) * 100
        if not math.isfinite(value):
            continue
        points.append({
            "label": _format_period_label(col),
            "value": round(value, 2),
        })
    if len(points) > limit:
        points = points[-limit:]
    return points


def _financial_indicators(ticker):
    data = {
        "roe": {"annual": [], "quarterly": []},
        "roa": {"annual": [], "quarterly": []},
        "eps": {"annual": [], "quarterly": []},
        "roce": {"annual": [], "quarterly": []},
        "dtar": {"annual": [], "quarterly": []},
    }
    if ticker is None:
        return data
    def _sanitize(points, max_abs=200):
        if not points:
            return []
        cleaned = []
        for point in points:
            try:
                value = float(point.get("value", 0))
            except Exception:
                continue
            if not math.isfinite(value):
                continue
            if abs(value) > max_abs:
                continue
            cleaned.append(point)
        return cleaned

    try:
        annual_financials = ticker.financials
        quarterly_financials = ticker.quarterly_financials
        annual_balance = ticker.balance_sheet
        quarterly_balance = ticker.quarterly_balance_sheet
        info = ticker.info or {}
    except Exception:
        return data

    roe_annual = _ratio_series(
        annual_financials,
        annual_balance,
        ["Net Income", "Net Income Common Stockholders", "Net Income Common"],
        ["Total Stockholder Equity", "Total Equity Gross Minority Interest"],
    )
    roe_quarterly = _ratio_series(
        quarterly_financials,
        quarterly_balance,
        ["Net Income", "Net Income Common Stockholders", "Net Income Common"],
        ["Total Stockholder Equity", "Total Equity Gross Minority Interest"],
    )
    roa_annual = _ratio_series(
        annual_financials,
        annual_balance,
        ["Net Income", "Net Income Common Stockholders", "Net Income Common"],
        ["Total Assets"],
    )
    roa_quarterly = _ratio_series(
        quarterly_financials,
        quarterly_balance,
        ["Net Income", "Net Income Common Stockholders", "Net Income Common"],
        ["Total Assets"],
    )
    eps_annual = _eps_series(annual_financials)
    eps_quarterly = _eps_series(quarterly_financials)
    roce_annual = _roce_series(annual_financials, annual_balance)
    roce_quarterly = _roce_series(quarterly_financials, quarterly_balance)
    dtar_annual = _dtar_series(annual_balance)
    dtar_quarterly = _dtar_series(quarterly_balance)

    data["roe"]["annual"] = _sanitize(roe_annual, max_abs=200)
    data["roe"]["quarterly"] = _sanitize(roe_quarterly, max_abs=200)
    data["roa"]["annual"] = _sanitize(roa_annual, max_abs=100)
    data["roa"]["quarterly"] = _sanitize(roa_quarterly, max_abs=100)
    data["eps"]["annual"] = _sanitize(eps_annual, max_abs=1_000_000)
    data["eps"]["quarterly"] = _sanitize(eps_quarterly, max_abs=1_000_000)
    data["roce"]["annual"] = _sanitize(roce_annual, max_abs=200)
    data["roce"]["quarterly"] = _sanitize(roce_quarterly, max_abs=200)
    data["dtar"]["annual"] = _sanitize(dtar_annual, max_abs=200)
    data["dtar"]["quarterly"] = _sanitize(dtar_quarterly, max_abs=200)

    def _fallback_percent(value):
        try:
            val = float(value)
        except Exception:
            return None
        if not math.isfinite(val):
            return None
        if abs(val) <= 1:
            val = val * 100
        return round(val, 2)

    def _ensure_latest(metric_key, info_key):
        if data[metric_key]["annual"] or data[metric_key]["quarterly"]:
            return
        fallback = _fallback_percent(info.get(info_key))
        if fallback is None:
            return
        data[metric_key]["annual"] = [{"label": "TTM", "value": fallback}]

    _ensure_latest("roe", "returnOnEquity")
    _ensure_latest("roa", "returnOnAssets")
    _ensure_latest("roce", "returnOnCapitalEmployed")
    _ensure_latest("dtar", "debtToAssets")
    return data


@api_view(["GET"])
@permission_classes([AllowAny])
def stock_detail_api(request):
    query = (
        request.GET.get("q")
        or request.GET.get("symbol")
        or request.GET.get("company")
        or ""
    ).strip()
    if not query:
        return Response({"error": "symbol required"}, status=400)

    resolved = resolve_symbol(query)
    if not resolved:
        alias = _SYMBOL_ALIASES.get(query.upper())
        if alias:
            resolved = resolve_symbol(alias)
    if not resolved:
        return Response({"error": "Unknown symbol"}, status=404)

    symbol, company = resolved
    price_symbol = _SYMBOL_ALIASES.get(symbol, symbol)

    register_symbol(price_symbol)
    current_price = get_price(price_symbol)
    change_percent = get_change_percent(price_symbol)

    change_amount = None
    if current_price is not None and change_percent is not None:
        try:
            change_amount = round((current_price * change_percent) / 100, 2)
        except Exception:
            change_amount = None

    ticker = None
    info = {}
    news = []
    try:
        ticker = yf.Ticker(f"{price_symbol}.NS")
        info = ticker.info or {}
        raw_news = ticker.news or []
        for item in raw_news:
            title = item.get("title")
            if not title:
                continue
            news.append({
                "title": title,
                "publisher": item.get("publisher") or "",
                "link": item.get("link") or "",
                "published": item.get("providerPublishTime"),
            })
    except Exception:
        news = []
        info = {}

    if not news:
        query = company or symbol
        try:
            market_news = get_market_news(query, force_refresh=True)
        except Exception:
            market_news = []
        for item in market_news:
            title = item.get("title")
            if not title:
                continue
            news.append({
                "title": title,
                "publisher": item.get("source") or "",
                "link": item.get("url") or "",
                "published": _to_epoch(item.get("published_at") or ""),
            })

    fundamentals = _build_financials(info)
    technicals = _technical_indicators(price_symbol)
    company_financials = _company_financials(ticker)
    financial_indicators = _financial_indicators(ticker)
    shareholding, shareholding_mode, shareholding_note = _shareholding_data(ticker)
    structured_financials = _build_structured_financials(info, ticker)

    peers, peers_mode, peers_note = _build_peer_rows(price_symbol, company)

    chart_points, chart_low, chart_high, day_return = _intraday_chart(price_symbol)
    day_open = info.get("open") if info else None
    prev_close = info.get("previousClose") if info else None
    day_low = info.get("dayLow") if info else None
    day_high = info.get("dayHigh") if info else None
    for key, value in {
        "day_open": day_open,
        "prev_close": prev_close,
        "day_low": day_low,
        "day_high": day_high,
    }.items():
        try:
            if value is not None and not math.isfinite(float(value)):
                if key == "day_open":
                    day_open = None
                elif key == "prev_close":
                    prev_close = None
                elif key == "day_low":
                    day_low = None
                elif key == "day_high":
                    day_high = None
        except Exception:
            continue
    if day_low is None:
        day_low = chart_low
    if day_high is None:
        day_high = chart_high

    analysis = analyze_stock(symbol)
    if current_price is None:
        current_price = analysis.get("current_price")

    chart_times = [point.get("t") for point in chart_points] if chart_points else []
    chart_prices = [point.get("p") for point in chart_points] if chart_points else []
    chart_points_xy = [
        [point.get("ts"), point.get("p")]
        for point in chart_points
        if point.get("ts") is not None
    ]

    return Response({
        "symbol": symbol,
        "company": company.title() if company else symbol,
        "exchange": _exchange_for_symbol(symbol),
        "current_price": current_price,
        "change_percent": change_percent,
        "change_amount": change_amount,
        "prediction": analysis.get("prediction", {}).get("tomorrow", {}),
        "trend": analysis.get("trend", {}),
        "sentiment": analysis.get("sentiment", {}),
        "risk": analysis.get("risk", {}),
        "confidence": analysis.get("confidence", {}),
        "signal": analysis.get("signal"),
        "news": news,
        "financials": fundamentals,
        "fundamentals": fundamentals,
        "technicals": technicals,
        "company_financials": company_financials,
        "financial_indicators": financial_indicators,
        "snapshot": structured_financials.get("snapshot", {}),
        "balance_sheet": structured_financials.get("balance_sheet", {}),
        "cashflow": structured_financials.get("cashflow", {}),
        "ratios": structured_financials.get("ratios", {}),
        "quality": structured_financials.get("quality", {}),
        "last_updated": structured_financials.get("last_updated"),
        "peers_mode": peers_mode,
        "peers_note": peers_note,
        "peers": peers,
        "shareholding": shareholding,
        "shareholding_mode": shareholding_mode,
        "shareholding_note": shareholding_note,
        "chart": chart_points,
        "chart_times": chart_times,
        "chart_prices": chart_prices,
        "chart_points": chart_points_xy,
        "chart_available": bool(chart_points),
        "today_low": day_low,
        "today_high": day_high,
        "today_return": day_return,
        "today_open": day_open,
        "previous_close": prev_close,
    })

