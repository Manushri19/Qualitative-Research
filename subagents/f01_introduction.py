import os
from pathlib import Path
from typing import Dict, Any
from loguru import logger

from tools.financial_calculator import FinancialCalculator

class BaseAgent:
    """Mock BaseAgent to allow standalone compilation if needed."""
    def __init__(self, agent_id, config, llm_client):
        self.agent_id = agent_id
        self.config = config
        self.llm_client = llm_client

class BaseLLMClient:
    """Mock BaseLLMClient for typing."""
    def complete(self, system: str, user: str) -> str:
        pass

class F01IntroductionAgent(BaseAgent):
    """
    Analyses ROIC vs WACC, trend direction, and future value creation percentage.
    Produces analyst-style narrative and structured findings for context broker.
    """
    
    HARDCODED_OUTPUT_SCHEMA = {
        "agent_id": "F01",
        "key_finding": "",
        "status": "success",
        "findings": {
            "roic_above_wacc": False,
            "latest_roic": 0.0,
            "latest_roce": 0.0,
            "wacc": 0.0,
            "roic_spread": 0.0,
            "trend_direction": "stable",
            "trend_consistency": "mixed",
            "peak_roic": {"year": "N/A", "value": 0.0},
            "trough_roic": {"year": "N/A", "value": 0.0},
            "future_value_pct": 0.0,
            "pb_ratio": 0.0,
            "revenue_trend": "stable",
            "margin_trend": "stable",
            "value_creating": False,
            "years_analysed": 0,
            "data_quality_flags": []
        },
        "output": ""
    }

    def __init__(self, config: dict, llm_client: Any, session: dict):
        """
        Calls super().__init__("F01", config, llm_client)
        Stores session (wacc, stock_price, shares_outstanding)
        Initialises FinancialCalculator
        """
        super().__init__("F01", config, llm_client)
        self.session = session
        self.financial_calc = FinancialCalculator()
        self.metric_map = {
            "ebit": ["ebit", "operating profit", "profit before interest and tax", "pbit"],
            "tax_rate": ["effective tax rate", "tax rate", "income tax rate"],
            "total_equity": ["total equity", "shareholders equity", "net worth"],
            "total_debt": ["total debt", "total borrowings", "long term debt + short term debt"],
            "cash_equivalents": ["cash and cash equivalents", "cash and bank balances", "cash equivalents"],
            "total_assets": ["total assets"],
            "current_liabilities": ["current liabilities", "total current liabilities"],
            "revenue": ["revenue", "net revenue", "total revenue", "net sales", "total income from operations"],
            "ebitda": ["ebitda", "operating profit before depreciation"],
            "pat": ["pat", "profit after tax", "net profit", "profit for the year"]
        }

    def load_financials(self, context_package: dict) -> dict:
        """
        Extracts yearly_master and quarterly_master from context_package["financials"].
        Returns them as separate dicts.
        Raises ValueError if financials missing from package.
        """
        fins = context_package.get("financials", {})
        yearly = fins.get("yearly")
        quarterly = fins.get("quarterly")
        if yearly is None or quarterly is None:
            raise ValueError("Missing financials in context_package")
        return {"yearly_master": yearly, "quarterly_master": quarterly}

    def run_calculations(self, yearly_master: dict, session: dict) -> dict:
        """
        Runs all FinancialCalculator methods in sequence.
        Collects all outputs into single calculations dict.
        Logs any None values encountered as data quality flags.
        """
        flags = []
        
        wacc = session.get("wacc", 10.0)
        stock_price = session.get("stock_price", 0.0)
        shares = session.get("shares_outstanding", 0)
        
        roic_roce = self.financial_calc.compute_roic_roce_series(yearly_master, self.metric_map)
        trend = self.financial_calc.analyse_roic_trend(roic_roce, wacc)
        fv = self.financial_calc.compute_future_value_percentage(stock_price, shares, yearly_master, self.metric_map, wacc)
        rev_growth = self.financial_calc.compute_revenue_growth(yearly_master, self.metric_map)
        margins = self.financial_calc.compute_margin_series(yearly_master, self.metric_map)
        
        for missing_year in trend.get("years_with_missing_data", []):
            flags.append(f"Missing ROIC data for {missing_year}")
            
        return {
            "roic_roce_series": roic_roce,
            "trend_analysis": trend,
            "future_value": fv,
            "revenue_growth": rev_growth,
            "margins": margins,
            "data_quality_flags": flags
        }

    def build_prompt(self, context_package: dict, calculations: dict) -> str:
        """
        Loads f01_prompt.txt template.
        Injects data and narrative chunks into template.
        """
        base_dir = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        prompt_path = base_dir / "templates" / "prompts" / "f01_prompt.txt"
        
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                template = f.read()
        except FileNotFoundError:
            template = "{company_name}\n{metrics_table}\n{roic_wacc_table}\n{revenue_margin_table}\n{peer_roic_table}\n{narrative_chunks}"
            
        trend = calculations.get("trend_analysis", {})
        rev = calculations.get("revenue_growth", {})
        margins = calculations.get("margins", {})
        fv = calculations.get("future_value", {})
        
        latest_roic = trend.get("latest_roic", {}).get("value", 0.0)
        latest_roce = trend.get("latest_roce", {}).get("value", 0.0)
        wacc = self.session.get("wacc", 0.0)
        spread = round(latest_roic - wacc, 2)
        
        metrics_table = f"""Metric          | Latest Value | Trend
ROIC            | {latest_roic}%     | {trend.get('trend_direction', '-')}
ROCE            | {latest_roce}%     | -
WACC            | {wacc}%     | -
ROIC Spread     | {spread}%     | -
EBITDA Margin   | {margins.get('latest_ebitda_margin', 0.0)}%     | {margins.get('margin_trend', '-')}
PAT Margin      | {margins.get('latest_pat_margin', 0.0)}%     | {margins.get('margin_trend', '-')}
Revenue Growth  | {rev.get('yoy_growth', {}).get(trend.get('latest_roic', {}).get('year'), 0.0)}%     | {rev.get('revenue_trend', '-')}
Future Value %  | {fv.get('future_value_pct', 0.0)}%     | -
P/B Ratio       | {fv.get('pb_ratio', 0.0)}x     | -"""

        roic_wacc_table = "FY    | ROIC  | WACC  | Spread | Value Creating\n"
        for fy, data in trend.get("roic_vs_wacc_by_year", {}).items():
            roic_wacc_table += f"{fy} | {data.get('roic')}% | {data.get('wacc')}% | {data.get('spread')}% | {'Yes' if data.get('value_creating') else 'No'}\n"
            
        revenue_margin_table = "FY | Rev YoY % | EBITDA Margin % | PAT Margin %\n"
        for fy in calculations.get("roic_roce_series", {}).keys():
            yoy = rev.get("yoy_growth", {}).get(fy, "-")
            ebm = margins.get("ebitda_margin", {}).get(fy, "-")
            pam = margins.get("pat_margin", {}).get(fy, "-")
            revenue_margin_table += f"{fy} | {yoy}% | {ebm}% | {pam}%\n"

        peer_roic_table = "No peer data available in this package."

        narrative_chunks = ""
        for chunk in context_package.get("narrative", []):
            tags = chunk.get("tags", [])
            if "financials" in tags or "strategy" in tags:
                narrative_chunks += f"\n- {chunk.get('text', '')}"
                
        if not narrative_chunks:
            narrative_chunks = "No relevant narrative chunks found."
            
        start_year = "FY2015"
        end_year = "FY2025"
        sorted_years = sorted(calculations.get("roic_roce_series", {}).keys())
        if sorted_years:
            start_year = sorted_years[0]
            end_year = sorted_years[-1]

        prompt = template.replace("{company_name}", context_package.get("focal_company", "Unknown"))
        prompt = prompt.replace("{start_year}", start_year)
        prompt = prompt.replace("{end_year}", end_year)
        prompt = prompt.replace("{metrics_table}", metrics_table)
        prompt = prompt.replace("{roic_wacc_table}", roic_wacc_table)
        prompt = prompt.replace("{revenue_margin_table}", revenue_margin_table)
        prompt = prompt.replace("{peer_roic_table}", peer_roic_table)
        prompt = prompt.replace("{narrative_chunks}", narrative_chunks)
        
        return prompt

    def parse_llm_output(self, llm_response: str, calculations: dict) -> dict:
        """
        Parses LLM markdown response.
        Validates required sections.
        """
        # Extract KEY_FINDING
        key_finding = ""
        for line in llm_response.splitlines():
            if line.startswith("KEY_FINDING:"):
                key_finding = line.replace("KEY_FINDING:", "").strip()
                break
        
        if not key_finding or len(key_finding.split()) > 25:
            logger.warning(f"{self.agent_id} key finding missing or too long — using fallback")
            fallback = ""
            if "## Summary" in llm_response:
                summary_text = llm_response.split("## Summary")[1].strip()
                first_sentence = summary_text.split(".")[0] + "."
                fallback = " ".join(first_sentence.split()[:25])
            else:
                first_sentence = llm_response.split(".")[0] + "."
                fallback = " ".join(first_sentence.split()[:25])
            key_finding = fallback

        required_sections = [
            "## Overview",
            "## ROIC Analysis",
            "## Trend Analysis",
            "## Future Value Assessment",
            "## Key Risks to ROIC",
            "## Summary"
        ]
        
        for section in required_sections:
            if section not in llm_response:
                logger.warning(f"F01 LLM response missing section: {section}")
                llm_response += f"\n\n{section}\n*Analysis unavailable for this section.*"
                
        words = llm_response.split()
        if len(words) > 1200:
            logger.info(f"F01 LLM output trimmed from {len(words)} to 1200 words")
            trimmed = " ".join(words[:1200])
            last_period = trimmed.rfind(".")
            if last_period != -1:
                llm_response = trimmed[:last_period+1]
            else:
                llm_response = trimmed
                
        trend = calculations.get("trend_analysis", {})
        fv = calculations.get("future_value", {})
        rev = calculations.get("revenue_growth", {})
        margins = calculations.get("margins", {})
        
        latest_roic = trend.get("latest_roic", {}).get("value", 0.0)
        wacc = self.session.get("wacc", 0.0)
        spread = round(latest_roic - wacc, 2)
        
        findings = {
            "roic_above_wacc": spread > 0,
            "latest_roic": latest_roic,
            "latest_roce": trend.get("latest_roce", {}).get("value", 0.0),
            "wacc": wacc,
            "roic_spread": spread,
            "trend_direction": trend.get("trend_direction", "stable"),
            "trend_consistency": trend.get("trend_consistency", "mixed"),
            "peak_roic": trend.get("peak_roic", {}),
            "trough_roic": trend.get("trough_roic", {}),
            "future_value_pct": fv.get("future_value_pct", 0.0),
            "pb_ratio": fv.get("pb_ratio", 0.0),
            "revenue_trend": rev.get("revenue_trend", "stable"),
            "margin_trend": margins.get("margin_trend", "stable"),
            "value_creating": spread > 0,
            "years_analysed": trend.get("years_analysed", 0),
            "data_quality_flags": calculations.get("data_quality_flags", [])
        }
        
        result = self.HARDCODED_OUTPUT_SCHEMA.copy()
        result["key_finding"] = key_finding
        result["status"] = "success"
        result["findings"] = findings
        result["output"] = llm_response
        
        return result

    def run(self, context_package: dict) -> dict:
        """
        Master run method implementing BaseAgent.run()
        """
        try:
            fin_data = self.load_financials(context_package)
            calculations = self.run_calculations(fin_data["yearly_master"], self.session)
            prompt = self.build_prompt(context_package, calculations)
            
            system_prompt = "You are a senior equity research analyst."
            if "SYSTEM PROMPT" in prompt:
                pass
                
            llm_response = ""
            if self.llm_client:
                llm_response = self.llm_client.complete(system_prompt, prompt)
            else:
                llm_response = "## Overview\nTest\n## ROIC Analysis\nTest\n## Trend Analysis\nTest\n## Future Value Assessment\nTest\n## Key Risks to ROIC\nTest\n## Summary\nTest."
                
            result = self.parse_llm_output(llm_response, calculations)
            
            self.save_output(result)
            
            return result
        except Exception as e:
            logger.error(f"F01 run error: {e}", exc_info=True)
            failed = self.HARDCODED_OUTPUT_SCHEMA.copy()
            failed["status"] = "failed"
            failed["error"] = str(e)
            return failed
