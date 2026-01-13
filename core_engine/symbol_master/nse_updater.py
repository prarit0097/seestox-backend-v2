import pandas as pd
import requests
import os
from io import StringIO

NSE_EQUITY_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
OUTPUT_PATH = "core_engine/symbol_master/nse_master.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/csv",
    "Referer": "https://www.nseindia.com/"
}

def build_nse_master():
    print("📥 Downloading NSE EQUITY_L.csv ...")

    resp = requests.get(NSE_EQUITY_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    df = pd.read_csv(StringIO(resp.text))

    # Clean + standardize
    df = df.rename(columns={
        "SYMBOL": "symbol",
        "NAME OF COMPANY": "company_name"
    })

    df = df[["symbol", "company_name"]]
    df["symbol"] = df["symbol"].str.strip().str.upper()
    df["company_name"] = df["company_name"].str.strip()

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)

    print(f"✅ NSE Master built successfully: {len(df)} companies")
    print(f"📁 Saved at: {OUTPUT_PATH}")

if __name__ == "__main__":
    build_nse_master()
