# prism_client.py
import json
import logging
import requests
import sys
import time
import yaml
from typing import Tuple

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Load config
with open("config.yaml", "r") as f:
    cfg = yaml.safe_load(f)

TEAM_API_CODE = cfg.get("team_api_code")
URL = cfg.get("server_host", "www.prism-challenge.com")
PORT = cfg.get("server_port", 8082)
BASE = f"http://{URL}:{PORT}"

if not TEAM_API_CODE or "PUT_YOUR_TOKEN" in TEAM_API_CODE:
    logging.error("Please add your real API token to config.yaml under 'team_api_code'. Exiting.")
    sys.exit(1)


def _request(method: str, path: str, data=None, timeout=8) -> Tuple[bool, str]:
    headers = {"X-API-Code": TEAM_API_CODE}
    if method.upper() == "GET":
        try:
            r = requests.get(f"{BASE}{path}", headers=headers, timeout=timeout)
        except Exception as e:
            return False, f"Request error: {e}"
    else:
        headers["Content-Type"] = "application/json"
        try:
            r = requests.post(f"{BASE}{path}", headers=headers, data=json.dumps(data), timeout=timeout)
        except Exception as e:
            return False, f"Request error: {e}"

    if r.status_code != 200:
        return False, f"HTTP {r.status_code}: {r.text}"
    return True, r.text


def get_context():
    return _request("GET", "/request")


def get_my_current_information():
    return _request("GET", "/info")


def send_portfolio(weighted_stocks):
    # weighted_stocks: list of tuples like [("AAPL", 10), ("MSFT", 5)]
    payload = [{"ticker": t, "quantity": q} for t, q in weighted_stocks]
    # quick validation: no duplicates
    tickers = [t for t, _ in weighted_stocks]
    if len(set(tickers)) != len(tickers):
        return False, "Duplicate tickers in submission"
    return _request("POST", "/submit", data=payload)


def safe_print_json(maybe_json_str):
    try:
        obj = json.loads(maybe_json_str)
        print(json.dumps(obj, indent=2))
    except Exception:
        print(maybe_json_str)


def build_portfolio(investor):
    """
    Generates a valid portfolio based on investor context.
    investor: dict with keys like 'age', 'budget', 'interests'
    Returns: list of dicts [{"ticker": "AAPL", "quantity": 1}, ...]
    """
    budget = investor.get("budget", 5000)
    interests = investor.get("interests", [])
    age = investor.get("age", 40)

    # Determine risk (simplified)
    if age > 65 or budget < 10000:
        risk = "low"
    elif age > 45:
        risk = "medium"
    else:
        risk = "high"

    # Map interests to tickers
    sector_map = {
        "finance": ["JPM", "BAC"],
        "real estate": ["PLD", "O"],
        "energy": ["XOM", "CVX"],
        "transportation": ["UNP", "FDX"],
        "tech": ["AAPL", "MSFT"],
        "trade": ["WMT", "COST"],
        "gardening": ["WMT", "COST"]
    }

    # Collect tickers based on interests
    tickers = []
    for sector, stocks in sector_map.items():
        for interest in interests:
            if sector in interest.lower():
                tickers.extend(stocks)
    if not tickers:
        tickers = ["PG", "KO", "JNJ", "XOM", "UNP"]  # fallback low-risk portfolio

    # Mock prices (replace with live prices later)
    prices = {"PG": 150, "KO": 65, "JNJ": 160, "XOM": 120, "UNP": 235,
              "JPM": 210, "BAC": 40, "PLD": 125, "O": 55, "XOM": 120,
              "CVX": 150, "UNP": 235, "FDX": 275, "AAPL": 230, "MSFT": 430,
              "WMT": 66, "COST": 750}

    # Allocate budget evenly
    allocation = budget / len(tickers)
    portfolio = []
    used_tickers = set()
    for t in tickers:
        if t in used_tickers:
            continue  # avoid duplicates
        price = prices.get(t, 100)
        qty = int(allocation // price)
        if qty > 0:
            portfolio.append({"ticker": t, "quantity": qty})
            used_tickers.add(t)

    return portfolio


if __name__ == "__main__":
    logging.info("Fetching team info...")
    ok, info = get_my_current_information()
    if not ok:
        logging.error("Failed to get team info: %s", info)
    else:
        logging.info("Team info:")
        safe_print_json(info)

    logging.info("Requesting investor context...")
    ok, context = get_context()
    if not ok:
        logging.error("Failed to get context: %s", context)
        logging.info("Investor context received:")
    else:
        safe_print_json(context)

    # example dry-run portfolio (CHANGE before real submission!)
    sample_portfolio = [("AAPL", 1), ("MSFT", 1)]
    logging.info("Dry-run sending portfolio (comment out before real competition!)")
    ok, resp = send_portfolio(sample_portfolio)
    if not ok:
        logging.error("Submission failed (this is expected if server rejects): %s", resp)
    else:
        logging.info("Submission response:")
        safe_print_json(resp)
