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
    else:
        logging.info("Investor context received:")
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
