import os
import sys
from datetime import datetime
from dotenv import load_dotenv
import yaml
# pyrefly: ignore [missing-import]
from loguru import logger
from rich.console import Console

from tools.validator import validate
from orchestrator.orchestrator import Orchestrator
from llm.client import get_llm_client
def get_financial_inputs(focal_company: str) -> dict:
    """
    Collects all financial inputs at startup in one sequential CLI session using rich console.
    """
    console = Console()
    
    while True:
        console.print("─────────────────────────────────────────")
        console.print("  FINANCIAL INPUT REQUIRED")
        console.print("─────────────────────────────────────────")
        console.print(f"  Focal Company: {focal_company}")
        console.print("─────────────────────────────────────────")
        
        # [1/4] WACC (%)
        wacc = None
        while wacc is None:
            console.print(f"\n[1/4] Enter WACC (%) for {focal_company}:")
            console.print("      (e.g. 12.5 for 12.5%)")
            console.print("      Source suggestion: Damodaran India dataset")
            try:
                val = input("> ")
                temp = float(val.strip())
                if 1.0 <= temp <= 50.0:
                    wacc = temp
                else:
                    console.print("[red]Warning: WACC must be between 1.0 and 50.0. Please re-enter.[/red]")
            except ValueError:
                console.print("[red]Warning: Invalid float. Please re-enter.[/red]")
                
        # [2/4] Stock Price
        stock_price = None
        while stock_price is None:
            console.print(f"\n[2/4] Enter current stock price (INR):")
            try:
                val = input("> ")
                temp = float(val.strip())
                if temp > 0:
                    stock_price = temp
                else:
                    console.print("[red]Warning: Stock price must be > 0. Please re-enter.[/red]")
            except ValueError:
                console.print("[red]Warning: Invalid float. Please re-enter.[/red]")
                
        # [3/4] Shares Outstanding
        shares_outstanding = None
        while shares_outstanding is None:
            console.print(f"\n[3/4] Enter shares outstanding:")
            console.print("      (in units, e.g. 3650000000)")
            try:
                val = input("> ")
                temp = int(val.strip())
                if temp > 0:
                    shares_outstanding = temp
                else:
                    console.print("[red]Warning: Shares must be > 0. Please re-enter.[/red]")
            except ValueError:
                console.print("[red]Warning: Invalid integer. Please re-enter.[/red]")
                
        # [4/4] Industry Context
        industry_roic = None
        while industry_roic is None:
            console.print(f"\n[4/4] Enter current industry ROIC (%):")
            console.print("      (e.g. 15.0 for 15.0%)")
            try:
                val = input("> ")
                temp = float(val.strip())
                if 1.0 <= temp <= 100.0:
                    industry_roic = temp
                else:
                    console.print("[red]Warning: Industry ROIC must be between 1.0 and 100.0. Please re-enter.[/red]")
            except ValueError:
                console.print("[red]Warning: Invalid float. Please re-enter.[/red]")
                
        industry_roic_trend = None
        while industry_roic_trend is None:
            console.print("\nSelect industry ROIC trend:")
            console.print("  [1] Improving")
            console.print("  [2] Stable")
            console.print("  [3] Deteriorating")
            val = input("> ").strip()
            if val == "1":
                industry_roic_trend = "improving"
            elif val == "2":
                industry_roic_trend = "stable"
            elif val == "3":
                industry_roic_trend = "deteriorating"
            else:
                console.print("[red]Warning: Must enter 1, 2, or 3. Please re-enter.[/red]")
                
        console.print("\n─────────────────────────────────────────")
        console.print("  Input Summary")
        console.print("─────────────────────────────────────────")
        console.print(f"  WACC:                  {wacc}%")
        console.print(f"  Stock Price:           ₹{stock_price:,.2f}")
        console.print(f"  Shares Outstanding:    {shares_outstanding:,}")
        console.print(f"  Industry ROIC:         {industry_roic}%")
        console.print(f"  Industry ROIC Trend:   {industry_roic_trend}")
        console.print("─────────────────────────────────────────")
        
        confirm = input("  Proceed? (y/n): ").strip().lower()
        if confirm == 'y':
            return {
                "wacc": wacc,
                "stock_price": stock_price,
                "shares_outstanding": shares_outstanding,
                "industry_roic": industry_roic,
                "industry_roic_trend": industry_roic_trend
            }

def main():
    # 1. Load .env using python-dotenv
    load_dotenv()

    # 2. Load config.yaml using pyyaml
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print("Error: config.yaml not found.")
        sys.exit(1)

    # Extract required config values
    focal_company = config.get("run", {}).get("focal_company", "")
    peer_comps = config.get("run", {}).get("peer_comps", [])
    model_name = config.get("model", {}).get("model_name", "")
    date_range_start = config.get("run", {}).get("date_range", {}).get("start", "")
    date_range_end = config.get("run", {}).get("date_range", {}).get("end", "")
    logs_dir = config.get("paths", {}).get("logs_dir", "logs")

    # 3. Set up loguru logger writing to /logs/{focal_company}_{date}.log
    current_date = datetime.now().strftime("%Y%m%d")
    log_filename = f"{focal_company}_{current_date}.log" if focal_company else f"run_{current_date}.log"
    log_path = os.path.join(os.path.dirname(__file__), logs_dir, log_filename)
    logger.add(log_path, rotation="10 MB", level="INFO")

    # 4. Print a rich console banner
    console = Console()
    console.print("[bold cyan]HEDGE FUND QUALITATIVE RESEARCH AGENT[/bold cyan]")
    console.print(f"Focal Company: {focal_company}")
    console.print(f"Peer Comps: {peer_comps}")
    console.print(f"Model: {model_name}")
    console.print(f"Date Range: {date_range_start} to {date_range_end}")

    # 5. Call validator.py — if validation fails, print the exact error message and sys.exit(1)
    is_valid, error_msg = validate(config)
    if not is_valid:
        console.print(error_msg)
        sys.exit(1)

    # 6. Print "Validation passed. Ready to run pipeline."
    console.print("Validation passed. Ready to run pipeline.")

    # Get runtime financial inputs
    session = get_financial_inputs(focal_company)

    # 7. Add a placeholder comment: # TODO: pass session to orchestrator.run(session)
    llm_client = get_llm_client(config)
    orchestrator = Orchestrator(config, llm_client)
    orchestrator.run(session)

# 8. At the bottom, if __name__ == "__main__": call main()
if __name__ == "__main__":
    main()
