import os
import json
import logging
import requests
import sys
import yaml
import yfinance as yf
from typing import Tuple, List, Dict, Set

while True:
    # --- Optional AI Parsing ---
    try:
        import openai
    except ImportError:
        openai = None
        logging.warning("openai library not found. AI parsing will be disabled.")

    # --- Logging ---
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    # --- Load Config ---
    try:
        with open("config.yaml", "r") as f:
            cfg = yaml.safe_load(f)
    except FileNotFoundError:
        logging.error("config.yaml not found. Please create one.")
        sys.exit(1)

    # --- Constants ---
    TEAM_API_CODE = cfg.get("team_api_code")
    URL = cfg.get("server_host", "www.prism-challenge.com")
    PORT = cfg.get("server_port", 8082)
    BASE = f"http://{URL}:{PORT}"
    OPENAI_API_KEY = cfg.get("openai_api_key")

    # Set to True to build a portfolio but not submit it
    DRY_RUN = False  # Set to False to submit

    # --- Stock Universe Definitions ---
    SECTOR_MAP = {
        "finance": ["JPM", "BAC"],
        "real estate": ["PLD", "O"],
        "energy": ["XOM", "CVX"],
        "transportation": ["UNP", "FDX"],
        "tech": ["AAPL", "MSFT"],
        "trade": ["WMT", "COST"],
        "gardening": ["WMT", "COST"],
        "life sciences": ["JNJ", "PFE"],
        "crypto": ["COIN", "MSTR"]
    }
    FALLBACK_TICKERS = ["PG", "KO", "JNJ", "XOM", "UNP"]
    RISK_RATED_STOCKS = {
        "low": ["JNJ", "PG", "KO", "O", "WMT", "COST"],
        "medium": ["AAPL", "MSFT", "JPM", "BAC", "XOM", "CVX", "UNP", "FDX", "PFE", "PLD"],
        "high": ["COIN", "MSTR"]
    }
    BUDGET_ALLOCATIONS = {
        "conservative": [0.70, 0.30, 0.0],  # 70% low, 30% med, 0% high
        "moderate": [0.30, 0.60, 0.10],  # 30% low, 60% med, 10% high
        "aggressive": [0.10, 0.50, 0.40]  # 10% low, 50% med, 40% high
    }

    # --- API Key Validations ---
    if not TEAM_API_CODE or "PUT_YOUR_TOKEN" in TEAM_API_CODE:
        logging.error("Please add your real API token to config.yaml under 'team_api_code'. Exiting.")
        sys.exit(1)
    if OPENAI_API_KEY and openai:
        openai.api_key = OPENAI_API_KEY
        logging.info("OpenAI API key loaded.")
    elif not OPENAI_API_KEY and openai:
        logging.warning("OpenAI library is installed, but no API key found in config.yaml.")
        openai = None  # Disable it


    # --- Helper Functions ---
    def safe_print_json(data):
        """Prints a JSON string or Python object with indentation."""
        try:
            if isinstance(data, str):
                obj = json.loads(data)
            else:
                obj = data
            print(json.dumps(obj, indent=2))
        except json.JSONDecodeError:
            print(data)  # Print as-is if not JSON
        except Exception as e:
            logging.error(f"Error printing JSON: {e}")
            print(data)


    def get_risk_profile(age: int, budget: float) -> str:
        """Determine risk profile based on age AND budget."""
        if age >= 60 or budget < 20000:
            return "conservative"
        if age >= 40 or budget < 75000:
            return "moderate"
        return "aggressive"


    def _distribute_budget(
            budget_allocations: Dict[str, float],
            tickers: Set[str],
            budget: float
    ):
        """Helper to evenly distribute a budget among tickers."""
        if not tickers:
            return

        alloc_per_ticker = budget / len(tickers)
        for ticker in tickers:
            budget_allocations[ticker] = budget_allocations.get(ticker, 0) + alloc_per_ticker


    # --- Core API Functions ---
    def _request(method: str, path: str, data=None, timeout=10) -> Tuple[bool, str]:
        """Base function for making API requests to the server."""
        headers = {"X-API-Code": TEAM_API_CODE}
        url = f"{BASE}{path}"
        try:
            if method.upper() == "GET":
                r = requests.get(url, headers=headers, timeout=timeout)
            else:
                headers["Content-Type"] = "application/json"
                r = requests.post(url, headers=headers, data=json.dumps(data), timeout=timeout)
        except requests.exceptions.RequestException as e:
            return False, f"Request error: {e}"
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}: {r.text}"
        return True, r.text


    def get_context() -> Tuple[bool, str]:
        """Requests a new investor context."""
        return _request("GET", "/request")


    def get_my_current_information() -> Tuple[bool, str]:
        """Gets your team's current status."""
        return _request("GET", "/info")


    def send_portfolio(weighted_stocks: List[Tuple[str, int]]) -> Tuple[bool, str]:
        """Submit portfolio to server."""
        payload = [{"ticker": t, "quantity": q} for t, q in weighted_stocks]
        tickers = [t for t, _ in weighted_stocks]
        if len(set(tickers)) != len(tickers):
            logging.error(f"FATAL: Duplicate tickers in final submission: {tickers}")
            return False, "Duplicate tickers in submission"
        return _request("POST", "/submit", data=payload)


    # --- AI & Price Functions ---
    def parse_investor_string(investor_str: str) -> dict:
        """Use OpenAI to parse the investor string into structured fields."""
        if not openai or not OPENAI_API_KEY:
            logging.warning("OpenAI not available or API key not set. Using defaults.")
            return {"age": 40, "budget": 10000, "interests": [], "avoid_list": []}

        prompt = f"""
        Extract the following info from this text. Return JSON only.
        Text: {investor_str}
    
        JSON keys:
        - age (int, default to 40)
        - budget (float, default to 10000)
        - interests (list of strings, e.g., ["tech", "finance"])
        - avoid_list (list of strings, e.g., ["energy", "AAPL"])
        """
        try:
            client = openai.OpenAI(api_key=OPENAI_API_KEY)
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0
            )
            content = response.choices[0].message.content.strip()
            data = json.loads(content)
            return data
        except Exception as e:
            logging.warning(f"AI parsing failed: {e}. Returning defaults.")
            return {"age": 40, "budget": 10000, "interests": [], "avoid_list": []}


    def get_live_prices(tickers: List[str]) -> Dict[str, float]:
        """Fetches the current or previous close price for a list of tickers."""
        if not tickers:
            return {}
        logging.info(f"Fetching prices for: {', '.join(tickers)}")
        prices = {}
        try:
            tickers_obj = yf.Tickers(" ".join(tickers))
            for ticker in tickers:
                try:
                    info = tickers_obj.tickers[ticker].fast_info
                    price = info.get('regularMarketPrice', info.get('previousClose'))
                    if price:
                        prices[ticker] = price
                    else:
                        logging.warning(f"No price data for {ticker}, it will be skipped.")
                except Exception:
                    logging.warning(f"Failed to get price for {ticker}, skipping.")
            logging.info(f"Successfully got {len(prices)} prices.")
            return prices
        except Exception as e:
            logging.error(f"yfinance failed to fetch ticker data: {e}")
            return {}


    # --- NEW: "Pool Filling" Portfolio Logic ---
    def build_pool_filling_portfolio(investor_data: dict, prices: Dict[str, float]) -> List[dict]:
        """
        Builds a portfolio that strictly follows risk allocations,
        while prioritizing interests to fill each risk pool.
        """

        budget = investor_data.get("budget", 10000)
        interests = investor_data.get("interests", [])
        avoid_list = investor_data.get("avoid_list", [])
        age = investor_data.get("age", 40)

        # 1. Determine Risk Profile and Budget Allocations
        risk_profile = get_risk_profile(age, budget)
        logging.info(f"Investor age {age}, budget ${budget} -> {risk_profile} profile.")

        alloc_pcts = BUDGET_ALLOCATIONS[risk_profile]
        risk_budgets = {
            "low": budget * alloc_pcts[0],
            "medium": budget * alloc_pcts[1],
            "high": budget * alloc_pcts[2]
        }

        # 2. Create Final "Veto" List
        final_avoid_tickers = set()
        avoid_set = set(a.lower() for a in avoid_list)
        for item in avoid_set:
            if item in SECTOR_MAP:
                final_avoid_tickers.update(SECTOR_MAP[item])
            else:
                final_avoid_tickers.add(item.upper())
        if final_avoid_tickers:
            logging.info(f"Final Veto List: {final_avoid_tickers}")

        # 3. Create Interest Set
        interest_tickers = set()
        interest_set = set(i.lower() for i in interests)
        for sector, stocks in SECTOR_MAP.items():
            if sector in interest_set:
                interest_tickers.update(stocks)

        # 4. Define all available stocks for each risk level
        all_stocks_by_risk = {
            "low": set(RISK_RATED_STOCKS["low"]),
            "medium": set(RISK_RATED_STOCKS["medium"]),
            "high": set(RISK_RATED_STOCKS["high"])
        }

        # 5. --- NEW "Pool Filling" LOGIC ---
        # This dict will hold the final $ allocation for each ticker
        final_budget_allocations = {}

        for risk_level in ["low", "medium", "high"]:
            budget_for_level = risk_budgets[risk_level]
            if budget_for_level <= 0:
                continue  # Skip this risk level entirely if budget is 0

            # Find stocks that match this risk level AND are in interests
            stocks_to_buy = (all_stocks_by_risk[risk_level] & interest_tickers) - final_avoid_tickers

            # **The Fallback**: If no interested stocks match, use *all* stocks from this
            # risk level as candidates (that aren't vetoed).
            if not stocks_to_buy:
                logging.info(f"No interested stocks for {risk_level} pool. Using all {risk_level} stocks.")
                stocks_to_buy = all_stocks_by_risk[risk_level] - final_avoid_tickers

            if not stocks_to_buy:
                logging.warning(f"No stocks available for {risk_level} pool after veto. Budget wasted.")
                continue

            # Distribute the budget for this level among the chosen stocks
            logging.info(f"Allocating ${budget_for_level:.2f} to {risk_level} pool ({list(stocks_to_buy)})")
            _distribute_budget(final_budget_allocations, stocks_to_buy, budget_for_level)

        # 6. Convert final $ allocations into share quantities
        final_portfolio = []
        for ticker, allocation in final_budget_allocations.items():
            # Veto check is already done, but we double-check price
            price = prices.get(ticker)
            if not price:
                logging.warning(f"No price for {ticker}, cannot buy.")
                continue

            if allocation >= price:
                quantity = int(allocation // price)
                if quantity > 0:
                    final_portfolio.append({"ticker": ticker, "quantity": quantity})

        # 7. Emergency Fallback (if portfolio is *still* empty)
        if not final_portfolio:
            logging.error("Portfolio is empty after allocation. This should not happen.")
            # Emergency fallback: buy one share of a low-risk stock
            for ticker in all_stocks_by_risk["low"]:
                if ticker not in final_avoid_tickers and prices.get(ticker):
                    if budget >= prices[ticker]:
                        logging.warning(f"Emergency Fallback: Buying 1 share of {ticker}.")
                        final_portfolio.append({"ticker": ticker, "quantity": 1})
                        break

        return final_portfolio


    # --- Main Execution ---
    if __name__ == "__main__":
        logging.info("--- Starting Prism Client (Pool Filling Version) ---")

        # 1. Get Team Info
        logging.info("Fetching team info...")
        ok, info = get_my_current_information()
        if ok:
            safe_print_json(info)
        else:
            logging.error(f"Failed to get team info: {info}")

        # 2. Get Investor Context
        logging.info("Requesting investor context...")
        ok, context_json = get_context()
        if not ok:
            logging.error(f"Failed to get investor context: {context_json}")
            sys.exit(1)
        logging.info("Investor context received:")
        safe_print_json(context_json)

        # 3. Parse Context
        investor_str = json.loads(context_json).get("message", "")
        if not investor_str:
            logging.error("Context message was empty. Exiting.")
            sys.exit(1)
        investor_data = parse_investor_string(investor_str)
        logging.info("Parsed investor data:")
        safe_print_json(investor_data)

        # 4. Get Prices
        logging.info("Pre-fetching prices for all potential stocks...")
        all_potential_tickers = set()
        for stocks in SECTOR_MAP.values():
            all_potential_tickers.update(stocks)
        all_potential_tickers.update(FALLBACK_TICKERS)
        for stocks in RISK_RATED_STOCKS.values():
            all_potential_tickers.update(stocks)
        live_prices = get_live_prices(list(all_potential_tickers))
        if not live_prices:
            logging.error("Could not fetch any live prices! Using mock prices as fallback.")
            live_prices = {t: 100.0 for t in all_potential_tickers}

        # 5. Build Portfolio
        logging.info("Building risk-aware 'pool filling' portfolio...")
        # --- Renamed function call ---
        portfolio_dicts = build_pool_filling_portfolio(investor_data, live_prices)
        portfolio_tuples = [(p["ticker"], p["quantity"]) for p in portfolio_dicts]

        logging.info("--- Final Portfolio ---")
        safe_print_json(portfolio_dicts)
        # -----------------------------

        # 6. Submit (or show dry-run)
        if DRY_RUN:
            logging.warning("DRY_RUN is True. Portfolio will NOT be submitted.")
        else:
            if not portfolio_tuples:
                logging.warning("Portfolio is empty. Nothing to submit.")
            else:
                logging.info("DRY_RUN is False. Submitting portfolio...")
                ok, resp = send_portfolio(portfolio_tuples)
                if ok:
                    logging.info("Portfolio submitted successfully!")
                    safe_print_json(resp)
                else:
                    logging.error(f"Submission failed: {resp}")

        logging.info("--- Run complete ---")