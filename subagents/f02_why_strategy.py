import os
from pathlib import Path
from typing import Dict, Any
from loguru import logger

from tools.financial_calculator import FinancialCalculator
from subagents.base_agent import BaseAgent
from llm.client import BaseLLMClient

class F02WhyStrategyAgent(BaseAgent):
    """
    Analyses industry ROIC context, variance across peer set, 
    and gross margin as markup proxy. Reads F01 findings from 
    context broker to build a continuous analytical narrative.
    """
    
    HARDCODED_OUTPUT_SCHEMA = {
        "agent_id": "F02",
        "key_finding": "",
        "status": "success",
        "findings": {
            "industry_roic_input": 0.0,
            "industry_roic_trend": "stable",
            "peer_mean_roic_latest": 0.0,
            "peer_roic_variance_latest": 0.0,
            "peer_roic_std_dev_latest": 0.0,
            "focal_vs_industry": 0.0,
            "focal_rank_in_peer_set": 0,
            "gross_margin_latest": 0.0,
            "gross_margin_trend": "stable",
            "markup_trend": "stable",
            "industry_attractiveness": "medium",
            "strategy_matters_strength": "moderate",
            "f01_roic_referenced": False,
            "data_quality_flags": []
        },
        "output": ""
    }

    def __init__(self, config: dict, llm_client: BaseLLMClient, session: dict):
        """
        Calls super().__init__("F02", config, llm_client)
        Stores session dict
        Initialises FinancialCalculator
        """
        super().__init__("F02", config, llm_client)
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
            "revenue": ["revenue", "net revenue", "total revenue", "net sales", "revenue from operations"],
            "gross_profit": ["gross profit", "gross margin", "revenue from operations - cost of materials", "net revenue - cost of goods sold"],
            "cogs": ["cost of goods sold", "cost of materials consumed", "cost of revenue", "direct costs"]
        }

    def load_f01_findings(self, broker: Any) -> dict:
        """
        Reads F01 findings from context broker.
        """
        try:
            f01_findings = broker.read("F01")
            if not f01_findings:
                logger.warning("F01 findings not available in context broker. F02 will proceed without F01 context — narrative continuity may be affected.")
                return {}
            return f01_findings
        except Exception as e:
            logger.warning(f"F01 findings not available in context broker. F02 will proceed without F01 context — narrative continuity may be affected. Error: {e}")
            return {}

    def run_calculations(self, context_package: dict, session: dict, f01_findings: dict) -> dict:
        """
        Runs all F02-specific calculations.
        """
        flags = []
        
        fins = context_package.get("financials", {})
        yearly_master = fins.get("yearly", {})
        peer_financials = fins.get("peers", {})
        
        focal_ticker = self.config.get("run", {}).get("focal_company", "Unknown")
        
        gm_series = self.financial_calc.compute_gross_margin_series(yearly_master, self.metric_map)
        gm_trend = self.financial_calc.analyse_gross_margin_trend(gm_series)
        
        peer_roic_series = self.financial_calc.compute_peer_roic_series(peer_financials, self.metric_map)
        
        # focal_roic_series
        # "focal_roic_series, <- from F01 broker findings if available, else recalculate"
        focal_roic_series = {}
        if f01_findings and "roic_roce_series" in f01_findings:
            focal_roic_series = f01_findings["roic_roce_series"]
        else:
            focal_roic_series = self.financial_calc.compute_roic_roce_series(yearly_master, self.metric_map)
            
        industry_stats = self.financial_calc.compute_industry_statistics(
            focal_ticker,
            focal_roic_series,
            peer_roic_series,
            session.get("industry_roic", 0.0),
            session.get("industry_roic_trend", "stable")
        )
        
        # industry_attractiveness logic (hardcoded)
        wacc = session.get("wacc", 10.0)
        industry_attractiveness = "medium"
        strategy_matters_strength = "moderate"
        
        latest_fy = None
        if industry_stats.get("per_year_stats"):
            latest_fy = max(industry_stats["per_year_stats"].keys())
            latest_stats = industry_stats["per_year_stats"][latest_fy]
            
            mean_roic = latest_stats.get("mean_roic", 0.0)
            if mean_roic > wacc + 3.0:
                industry_attractiveness = "high"
            elif mean_roic >= wacc:
                industry_attractiveness = "medium"
            else:
                industry_attractiveness = "low"
                
            std_dev = latest_stats.get("std_deviation", 0.0)
            if std_dev > 5.0:
                strategy_matters_strength = "strong"
            elif std_dev >= 2.0:
                strategy_matters_strength = "moderate"
            else:
                strategy_matters_strength = "weak"
        else:
            flags.append("Missing peer industry statistics to compute attractiveness and strength.")

        return {
            "gross_margin_series": gm_series,
            "gross_margin_trend": gm_trend,
            "peer_roic_series": peer_roic_series,
            "industry_stats": industry_stats,
            "industry_attractiveness": industry_attractiveness,
            "strategy_matters_strength": strategy_matters_strength,
            "data_quality_flags": flags
        }

    def build_prompt(self, context_package: dict, calculations: dict, f01_findings: dict) -> str:
        """
        Loads f02_prompt.txt template. Injects data.
        """
        base_dir = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        prompt_path = base_dir / "templates" / "prompts" / "f02_prompt.txt"
        
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                template = f.read()
        except FileNotFoundError:
            template = "{company_name}\n{f01_bridge_table}\n{industry_roic_table}\n{peer_roic_table}\n{variance_table}\n{gross_margin_table}\n{narrative_chunks}"
            
        focal_company = self.config.get("run", {}).get("focal_company", "Unknown")
        peer_set = self.config.get("run", {}).get("peer_comps", [])
        peer_set_str = ", ".join(peer_set) if peer_set else "None"
        
        # F01 Bridge Table
        f01_latest_roic = f01_findings.get("latest_roic", 0.0)
        wacc = f01_findings.get("wacc", self.session.get("wacc", 0.0))
        roic_spread = f01_findings.get("roic_spread", 0.0)
        roic_trend = f01_findings.get("trend_direction", "unknown")
        margin_trend = f01_findings.get("margin_trend", "unknown")
        
        f01_bridge_table = f"""Metric               | Value
Focal ROIC (latest)  | {f01_latest_roic}%
WACC                 | {wacc}%
ROIC Spread          | {roic_spread}%
ROIC Trend           | {roic_trend}
EBITDA Margin Trend  | {margin_trend}"""

        # Industry ROIC Context table
        ind_stats = calculations.get("industry_stats", {})
        latest_fy = None
        if ind_stats.get("per_year_stats"):
            latest_fy = max(ind_stats["per_year_stats"].keys())
        latest_stats = ind_stats.get("per_year_stats", {}).get(latest_fy, {})
        
        industry_roic_table = f"""Source               | ROIC    | Trend
User-provided        | {self.session.get('industry_roic', 0.0)}%| {self.session.get('industry_roic_trend', '-')}
Peer set mean        | {latest_stats.get('mean_roic', 0.0)}%| calculated
Peer set median      | {latest_stats.get('median_roic', 0.0)}%| calculated"""

        # Peer ROIC Comparison table
        peer_roic_series = calculations.get("peer_roic_series", {})
        all_fys = set()
        for peer, series in peer_roic_series.items():
            all_fys.update(series.keys())
        all_fys = sorted(list(all_fys), reverse=True)[:5] # top 5 recent years
        
        header = "Company | " + " | ".join(all_fys)
        peer_roic_table = header + "\n"
        for peer, series in peer_roic_series.items():
            row = f"{peer} | "
            row += " | ".join([f"{series.get(fy, {}).get('roic', '-')}%\t" for fy in all_fys])
            peer_roic_table += row + "\n"
            
        mean_row = "Mean | "
        for fy in all_fys:
            mean_roic = ind_stats.get("per_year_stats", {}).get(fy, {}).get("mean_roic", "-")
            mean_row += f"{mean_roic}%\t | "
        peer_roic_table += mean_row
        
        # ROIC Variance table
        variance_table = "Year   | Mean  | Std Dev | Min        | Max\n"
        for fy in sorted(ind_stats.get("per_year_stats", {}).keys(), reverse=True)[:5]:
            st = ind_stats["per_year_stats"][fy]
            min_co = st.get("min_roic", {})
            max_co = st.get("max_roic", {})
            variance_table += f"{fy} | {st.get('mean_roic', '-')}% | {st.get('std_deviation', '-')}% | {min_co.get('company', '-')}: {min_co.get('value', '-')}% | {max_co.get('company', '-')}: {max_co.get('value', '-')}%\n"

        # Gross Margin table
        gm_series = calculations.get("gross_margin_series", {})
        gm_trend = calculations.get("gross_margin_trend", {})
        gross_margin_table = "Year   | Gross Margin% | YoY Change | Markup%\n"
        for fy in sorted(gm_series.keys(), reverse=True)[:5]:
            gm = gm_series[fy].get("gross_margin_pct", "-")
            yoy = gm_trend.get("yoy_change", {}).get(fy, "-")
            markup = gm_trend.get("markup_proxy", {}).get(fy, "-")
            gross_margin_table += f"{fy} | {gm}%        | {yoy}pp    | {markup}%\n"

        # Narrative chunks
        narrative_chunks = ""
        for chunk in context_package.get("narrative", []):
            tags = chunk.get("tags", [])
            if any(t in tags for t in ["financials", "strategy", "competition"]):
                narrative_chunks += f"\n- {chunk.get('text', '')}"
                
        if not narrative_chunks:
            narrative_chunks = "No relevant narrative chunks found."
            
        start_year = "FY2015"
        end_year = "FY2025"
        if ind_stats.get("per_year_stats"):
            fys_sorted = sorted(ind_stats["per_year_stats"].keys())
            start_year = fys_sorted[0]
            end_year = fys_sorted[-1]

        prompt = template.replace("{company_name}", focal_company)
        prompt = prompt.replace("{peer_set}", peer_set_str)
        prompt = prompt.replace("{start_year}", start_year)
        prompt = prompt.replace("{end_year}", end_year)
        prompt = prompt.replace("{f01_bridge_table}", f01_bridge_table)
        prompt = prompt.replace("{industry_roic_table}", industry_roic_table)
        prompt = prompt.replace("{peer_roic_table}", peer_roic_table)
        prompt = prompt.replace("{variance_table}", variance_table)
        prompt = prompt.replace("{gross_margin_table}", gross_margin_table)
        prompt = prompt.replace("{industry_attractiveness}", calculations.get("industry_attractiveness", "unknown"))
        prompt = prompt.replace("{strategy_matters_strength}", calculations.get("strategy_matters_strength", "unknown"))
        prompt = prompt.replace("{narrative_chunks}", narrative_chunks)
        
        return prompt

    def parse_llm_output(self, llm_response: str, calculations: dict, f01_findings: dict) -> dict:
        """
        Parses LLM output, applies validation and constructs output schema.
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
            "## Industry ROIC Overview",
            "## ROIC Variance Analysis",
            "## Industry Markup Analysis",
            "## Strategic Implications",
            "## Summary"
        ]
        
        for section in required_sections:
            if section not in llm_response:
                logger.warning(f"F02 LLM response missing section: {section}")
                llm_response += f"\n\n{section}\n*Analysis unavailable for this section.*"
                
        words = llm_response.split()
        if len(words) > 900:
            logger.info(f"F02 LLM output trimmed from {len(words)} to 900 words")
            trimmed = " ".join(words[:900])
            last_period = trimmed.rfind(".")
            if last_period != -1:
                llm_response = trimmed[:last_period+1]
            else:
                llm_response = trimmed

        ind_stats = calculations.get("industry_stats", {})
        gm_trend = calculations.get("gross_margin_trend", {})
        
        latest_fy = None
        if ind_stats.get("per_year_stats"):
            latest_fy = max(ind_stats["per_year_stats"].keys())
        latest_stats = ind_stats.get("per_year_stats", {}).get(latest_fy, {})
        
        findings = {
            "industry_roic_input": self.session.get("industry_roic", 0.0),
            "industry_roic_trend": self.session.get("industry_roic_trend", "stable"),
            "peer_mean_roic_latest": latest_stats.get("mean_roic", 0.0),
            "peer_roic_variance_latest": latest_stats.get("variance", 0.0),
            "peer_roic_std_dev_latest": latest_stats.get("std_deviation", 0.0),
            "focal_vs_industry": latest_stats.get("focal_vs_mean", 0.0),
            "focal_rank_in_peer_set": latest_stats.get("focal_rank", 0) if latest_stats.get("focal_rank") is not None else 0,
            "gross_margin_latest": gm_trend.get("latest_margin", {}).get("value", 0.0),
            "gross_margin_trend": gm_trend.get("trend_direction", "stable"),
            "markup_trend": gm_trend.get("markup_trend", "stable"),
            "industry_attractiveness": calculations.get("industry_attractiveness", "medium"),
            "strategy_matters_strength": calculations.get("strategy_matters_strength", "moderate"),
            "f01_roic_referenced": bool(f01_findings),
            "data_quality_flags": calculations.get("data_quality_flags", [])
        }
        
        result = self.HARDCODED_OUTPUT_SCHEMA.copy()
        result["key_finding"] = key_finding
        result["status"] = "success"
        result["findings"] = findings
        result["output"] = llm_response
        
        return result

    def run(self, context_package: dict, broker: Any = None) -> dict:
        """
        Master run method.
        Note: F02.run() takes broker as additional parameter.
        """
        try:
            f01_findings = self.load_f01_findings(broker) if broker else {}
            calculations = self.run_calculations(context_package, self.session, f01_findings)
            prompt = self.build_prompt(context_package, calculations, f01_findings)
            
            system_prompt = "You are a senior equity research analyst."
                
            llm_response = ""
            if self.llm_client:
                llm_response = self.llm_client.complete(system_prompt, prompt)
            else:
                llm_response = "## Industry ROIC Overview\nTest\n## ROIC Variance Analysis\nTest\n## Industry Markup Analysis\nTest\n## Strategic Implications\nTest\n## Summary\nTest."
                
            result = self.parse_llm_output(llm_response, calculations, f01_findings)
            
            self.save_output(result)
            
            if broker:
                broker.write("F02", result["findings"])
                
            return result
        except Exception as e:
            logger.error(f"F02 run error: {e}", exc_info=True)
            failed = self.HARDCODED_OUTPUT_SCHEMA.copy()
            failed["status"] = "failed"
            failed["error"] = str(e)
            
            self.save_output(failed)
            
            if broker:
                broker.write("F02", failed["findings"])
                
            return failed
