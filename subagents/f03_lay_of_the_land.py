import os
from pathlib import Path
from typing import Dict, Any, Optional
from loguru import logger

from tools.financial_calculator import FinancialCalculator
from subagents.base_agent import BaseAgent
from llm.client import BaseLLMClient

class F03LayOfTheLandAgent(BaseAgent):
    """
    Analyses competitive landscape, market share dynamics, 
    economic profit evolution, industry concentration, 
    and structure classification.
    Reads F01 and F02 findings from context broker.
    """

    HARDCODED_OUTPUT_SCHEMA = {
        "agent_id": "F03",
        "key_finding": "",
        "status": "success",
        "findings": {
            "proxy_market_share_latest": {},
            "focal_market_share_latest": 0.0,
            "focal_market_share_trend": "stable",
            "industry_share_stability": "stable",
            "focal_rank_latest": 0,
            "focal_rank_stable": True,
            "aggregate_ep_latest": 0.0,
            "aggregate_ep_trend": "stable",
            "focal_ep_latest": 0.0,
            "focal_ep_share_of_aggregate": 0.0,
            "latest_hhi": 0.0,
            "latest_cr4": 0.0,
            "hhi_classification": "competitive",
            "concentration_trend": "stable concentration",
            "industry_structure": "Moderately Competitive",
            "strategic_opportunities": "Niche dominance and operational efficiency",
            "rule_matched": 5,
            "data_quality_flags": []
        },
        "output": ""
    }

    def __init__(self, config: dict, llm_client: BaseLLMClient, session: dict):
        super().__init__("F03", config, llm_client)
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

    def load_broker_findings(self, broker: Any) -> dict:
        """
        Reads F01 and F02 findings from context broker.
        """
        results = {"F01": {}, "F02": {}}
        try:
            findings = broker.read_many(["F01", "F02"])
            f01 = findings.get("F01", {})
            f02 = findings.get("F02", {})
            if not f01:
                logger.warning("F01 findings missing from broker")
            if not f02:
                logger.warning("F02 findings missing from broker")
            results["F01"] = f01
            results["F02"] = f02
        except Exception as e:
            logger.warning(f"Failed to read broker findings: {e}")
        return results

    def run_calculations(self, context_package: dict, broker_findings: dict, session: dict) -> dict:
        """
        Runs all F03-specific calculations in sequence.
        """
        flags = []
        
        fins = context_package.get("financials", {})
        focal_yearly_master = fins.get("yearly", {})
        peer_financials = fins.get("peers", {})
        focal_ticker = self.config.get("run", {}).get("focal_company", "Unknown")
        wacc = session.get("wacc", 10.0)
        
        # STEP 1: Proxy Market Share
        proxy_market_share = self.financial_calc.compute_proxy_market_share(
            focal_ticker, focal_yearly_master, peer_financials, self.metric_map)
            
        # STEP 2: Market Share Stability
        market_share_stability = self.financial_calc.compute_market_share_stability(proxy_market_share)
        
        # STEP 3: Economic Profit Series
        f01 = broker_findings.get("F01", {})
        focal_roic_series = f01.get("roic_roce_series", {})
        if not focal_roic_series:
            focal_roic_series = self.financial_calc.compute_roic_roce_series(focal_yearly_master, self.metric_map)
            
        f02 = broker_findings.get("F02", {})
        peer_roic_series = f02.get("peer_roic_series", {})
        if not peer_roic_series:
            peer_roic_series = self.financial_calc.compute_peer_roic_series(peer_financials, self.metric_map)
            
        ep_series = self.financial_calc.compute_economic_profit_series(
            focal_ticker, focal_yearly_master, peer_financials, focal_roic_series, peer_roic_series, wacc, self.metric_map)
            
        # STEP 4: Concentration Metrics
        concentration_metrics = self.financial_calc.compute_concentration_metrics(proxy_market_share)
        
        # STEP 5: Classify Industry Structure
        industry_structure = self.financial_calc.classify_industry_structure(
            concentration_metrics, market_share_stability, f02)
            
        # STEP 6: Compute specific focal trends
        focal_market_share_trend = "stable"
        focal_rank_stable = True
        
        if focal_ticker in market_share_stability.get("per_company", {}):
            data = market_share_stability["per_company"][focal_ticker]
            if data.get("rank_changes", 0) > 1:
                focal_rank_stable = False
                
        fys = sorted([k for k in proxy_market_share.keys() if k != "methodology_note"])
        if len(fys) >= 4:
            recent_shares = []
            prior_shares = []
            for fy in fys[-2:]:
                if focal_ticker in proxy_market_share[fy]:
                    recent_shares.append(proxy_market_share[fy][focal_ticker]["market_share_pct"])
            for fy in fys[-4:-2]:
                if focal_ticker in proxy_market_share[fy]:
                    prior_shares.append(proxy_market_share[fy][focal_ticker]["market_share_pct"])
                    
            if recent_shares and prior_shares:
                recent_avg = sum(recent_shares) / len(recent_shares)
                prior_avg = sum(prior_shares) / len(prior_shares)
                if recent_avg - prior_avg > 0.5:
                    focal_market_share_trend = "gaining"
                elif prior_avg - recent_avg > 0.5:
                    focal_market_share_trend = "losing"
        
        return {
            "proxy_market_share": proxy_market_share,
            "market_share_stability": market_share_stability,
            "economic_profit": ep_series,
            "concentration_metrics": concentration_metrics,
            "industry_structure": industry_structure,
            "focal_market_share_trend": focal_market_share_trend,
            "focal_rank_stable": focal_rank_stable,
            "data_quality_flags": flags
        }

    def build_prompt(self, context_package: dict, calculations: dict, broker_findings: dict) -> str:
        """
        Loads f03_prompt.txt template. Injects data.
        """
        base_dir = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        prompt_path = base_dir / "templates" / "prompts" / "f03_prompt.txt"
        
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                template = f.read()
        except FileNotFoundError:
            template = "{company_name}\n{prior_findings_table}\n{market_share_table}\n{stability_table}\n{rank_table}\n{economic_profit_table}\n{concentration_table}\n{structure_classification}\n{narrative_chunks}"
            
        focal_company = self.config.get("run", {}).get("focal_company", "Unknown")
        peer_set = self.config.get("run", {}).get("peer_comps", [])
        peer_set_str = ", ".join(peer_set) if peer_set else "None"
        
        # Bridge table
        f01 = broker_findings.get("F01", {})
        f02 = broker_findings.get("F02", {})
        
        prior_findings_table = f"""Metric                    | Value  | Source
Focal ROIC (latest)       | {f01.get('latest_roic', '-')}% | F01
ROIC Trend                | {f01.get('trend_direction', '-')}  | F01
Industry Attractiveness   | {f02.get('industry_attractiveness', '-')}  | F02
Strategy Matters Strength | {f02.get('strategy_matters_strength', '-')}  | F02
Peer Mean ROIC            | {f02.get('peer_mean_roic_latest', '-')}% | F02"""

        # Proxy Market Share
        pms = calculations.get("proxy_market_share", {})
        fys = sorted([k for k in pms.keys() if k != "methodology_note"], reverse=True)[:4]
        fys_header = " | ".join(fys)
        market_share_table = f"Company | {fys_header} | Trend\n"
        
        stab = calculations.get("market_share_stability", {})
        all_comps = list(stab.get("per_company", {}).keys())
        
        for comp in all_comps:
            comp_trend = "stable"
            if comp == focal_company:
                comp_trend = calculations.get("focal_market_share_trend", "stable")
                
            row = f"{comp} | "
            for fy in fys:
                sh = pms.get(fy, {}).get(comp, {}).get("market_share_pct", "-")
                if sh != "-":
                    sh = f"{sh}%"
                row += f"{sh} | "
            row += comp_trend
            market_share_table += row + "\n"
            
        methodology_note = pms.get("methodology_note", "")

        # Market Share Stability
        stability_table = "Company | Mean Share | Std Dev | CV    | Stability\n"
        for comp, data in stab.get("per_company", {}).items():
            stability_table += f"{comp} | {data.get('mean_share_pct', '-')}% | {data.get('std_dev', '-')}% | {data.get('coefficient_of_variation', '-')} | {data.get('volatility_label', '-')}\n"
        stability_table += f"Industry Overall: {stab.get('industry_share_stability', '-')}"

        # Rank Stability
        rank_table = "Company | Modal Rank | Rank Changes | Stability\n"
        for comp, data in stab.get("per_company", {}).items():
            rank_table += f"{comp} | {data.get('modal_rank', '-')} | {data.get('rank_changes', '-')} | {data.get('rank_stability_label', '-')}\n"

        # EP Evolution
        ep = calculations.get("economic_profit", {})
        agg = ep.get("aggregate_by_year", {})
        ep_fys = sorted(list(agg.keys()), reverse=True)[:5]
        
        economic_profit_table = "Year   | Agg EP | Focal EP | Focal EP Share\n"
        for fy in ep_fys:
            a_ep = agg[fy].get("total_economic_profit", "-")
            f_ep = ep.get("per_company", {}).get(focal_company, {}).get(fy, {}).get("economic_profit", "-")
            f_share = "-"
            if a_ep != "-" and f_ep != "-" and a_ep != 0:
                f_share = round((f_ep / a_ep) * 100.0, 2)
            economic_profit_table += f"{fy} | {a_ep} | {f_ep} | {f_share}%\n"
        economic_profit_table += f"EP Trend: {ep.get('ep_trend', '-')}"

        # Concentration
        conc = calculations.get("concentration_metrics", {})
        conc_by_year = conc.get("by_year", {})
        conc_fys = sorted(list(conc_by_year.keys()), reverse=True)[:5]
        
        concentration_table = "Year   | HHI   | HHI Class    | CR4   | CR4 Class\n"
        for fy in conc_fys:
            d = conc_by_year[fy]
            concentration_table += f"{fy} | {d.get('hhi', '-')} | {d.get('hhi_classification', '-')} | {d.get('cr4', '-')}% | {d.get('cr4_classification', '-')}\n"
        concentration_table += f"Trend: {conc.get('concentration_trend', '-')}"

        # Structure
        struc = calculations.get("industry_structure", {})
        structure_classification = f"""Classification:      {struc.get('structure_classification', '-')}
Rationale:           {struc.get('classification_rationale', '-')}
Strategic Opps:      {struc.get('strategic_opportunities', '-')}
Rule Matched:        {struc.get('rule_matched', '-')}"""

        # Narrative chunks
        narrative_chunks = ""
        for chunk in context_package.get("narrative", []):
            tags = chunk.get("tags", [])
            if any(t in tags for t in ["competition", "strategy", "financials"]):
                narrative_chunks += f"\n- {chunk.get('text', '')}"
                
        if not narrative_chunks:
            narrative_chunks = "No relevant narrative chunks found."
            
        start_year = "FY2015"
        end_year = "FY2025"
        if fys:
            sorted_all_fys = sorted([k for k in pms.keys() if k != "methodology_note"])
            start_year = sorted_all_fys[0]
            end_year = sorted_all_fys[-1]

        prompt = template.replace("{company_name}", focal_company)
        prompt = prompt.replace("{peer_set}", peer_set_str)
        prompt = prompt.replace("{start_year}", start_year)
        prompt = prompt.replace("{end_year}", end_year)
        prompt = prompt.replace("{prior_findings_table}", prior_findings_table)
        prompt = prompt.replace("{market_share_table}", market_share_table)
        prompt = prompt.replace("{methodology_note}", methodology_note)
        prompt = prompt.replace("{stability_table}", stability_table)
        prompt = prompt.replace("{rank_table}", rank_table)
        prompt = prompt.replace("{economic_profit_table}", economic_profit_table)
        prompt = prompt.replace("{concentration_table}", concentration_table)
        prompt = prompt.replace("{structure_classification}", structure_classification)
        prompt = prompt.replace("{narrative_chunks}", narrative_chunks)
        
        return prompt

    def parse_llm_output(self, llm_response: str, calculations: dict, broker_findings: dict) -> dict:
        """
        Parses LLM markdown response.
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
            "## Competitive Landscape Overview",
            "## Market Share Analysis",
            "## Economic Profit Evolution",
            "## Industry Concentration",
            "## Industry Structure & Strategic Opportunities",
            "## Summary"
        ]
        
        for section in required_sections:
            if section not in llm_response:
                logger.warning(f"F03 LLM response missing section: {section}")
                llm_response += f"\n\n{section}\n*Analysis unavailable for this section.*"
                
        words = llm_response.split()
        if len(words) > 950:
            logger.info(f"F03 LLM output trimmed from {len(words)} to 950 words")
            trimmed = " ".join(words[:950])
            last_period = trimmed.rfind(".")
            if last_period != -1:
                llm_response = trimmed[:last_period+1]
            else:
                llm_response = trimmed
                
        pms = calculations.get("proxy_market_share", {})
        fys = sorted([k for k in pms.keys() if k != "methodology_note"])
        
        pms_latest = {}
        if fys:
            latest_fy = fys[-1]
            for k, v in pms[latest_fy].items():
                if k not in ["universe_revenue", "companies_included"]:
                    pms_latest[k] = v.get("market_share_pct", 0.0)
                    
        focal_ticker = self.config.get("run", {}).get("focal_company", "Unknown")
        stab = calculations.get("market_share_stability", {})
        ep = calculations.get("economic_profit", {})
        conc = calculations.get("concentration_metrics", {})
        struc = calculations.get("industry_structure", {})
        
        focal_rank = 0
        if focal_ticker in stab.get("per_company", {}):
            fys_ranks = sorted(stab["per_company"][focal_ticker].get("ranks_by_year", {}).keys())
            if fys_ranks:
                focal_rank = stab["per_company"][focal_ticker]["ranks_by_year"][fys_ranks[-1]]
                
        findings = {
            "proxy_market_share_latest": pms_latest,
            "focal_market_share_latest": pms_latest.get(focal_ticker, 0.0),
            "focal_market_share_trend": calculations.get("focal_market_share_trend", "stable"),
            "industry_share_stability": stab.get("industry_share_stability", "stable"),
            "focal_rank_latest": focal_rank,
            "focal_rank_stable": calculations.get("focal_rank_stable", True),
            "aggregate_ep_latest": ep.get("latest_aggregate_ep", 0.0),
            "aggregate_ep_trend": ep.get("ep_trend", "stable"),
            "focal_ep_latest": ep.get("focal_ep_latest", 0.0),
            "focal_ep_share_of_aggregate": ep.get("focal_ep_share_of_aggregate", 0.0),
            "latest_hhi": conc.get("latest_hhi", 0.0),
            "latest_cr4": conc.get("latest_cr4", 0.0),
            "hhi_classification": conc.get("latest_hhi_classification", "competitive"),
            "concentration_trend": conc.get("concentration_trend", "stable concentration"),
            "industry_structure": struc.get("structure_classification", "Moderately Competitive"),
            "strategic_opportunities": struc.get("strategic_opportunities", "Niche dominance and operational efficiency"),
            "rule_matched": struc.get("rule_matched", 5),
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
        """
        try:
            broker_findings = self.load_broker_findings(broker) if broker else {}
            calculations = self.run_calculations(context_package, broker_findings, self.session)
            prompt = self.build_prompt(context_package, calculations, broker_findings)
            
            system_prompt = "You are a senior equity research analyst."
                
            llm_response = ""
            if self.llm_client:
                llm_response = self.llm_client.complete(system_prompt, prompt)
            else:
                llm_response = "## Competitive Landscape Overview\nTest\n## Market Share Analysis\nTest\n## Economic Profit Evolution\nTest\n## Industry Concentration\nTest\n## Industry Structure & Strategic Opportunities\nTest\n## Summary\nTest."
                
            result = self.parse_llm_output(llm_response, calculations, broker_findings)
            
            self.save_output(result)
            
            if broker:
                broker.write("F03", result["findings"])
                
            return result
        except Exception as e:
            logger.error(f"F03 run error: {e}", exc_info=True)
            failed = self.HARDCODED_OUTPUT_SCHEMA.copy()
            failed["status"] = "failed"
            failed["error"] = str(e)
            
            self.save_output(failed)
            
            if broker:
                broker.write("F03", {})
                
            return failed
