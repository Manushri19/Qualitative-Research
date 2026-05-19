import os
import json
from pathlib import Path
from typing import Dict, Any, Tuple
from loguru import logger

from subagents.base_agent import BaseAgent
from llm.client import BaseLLMClient
from tools.financial_calculator import FinancialCalculator
from tools.qualitative_scorer import QualitativeScorer

class F06RivalryAgent(BaseAgent):
    """
    Analyses rivalry among existing firms using programmatic signals for demand variability,
    industry growth, and firm similarity, combined with rubric-based qualitative scoring
    for coordination, leadership, and rivalry intensity.
    """

    HARDCODED_OUTPUT_SCHEMA = {
        "agent_id": "F06",
        "key_finding": "",
        "status": "success",
        "findings": {
            "rivalry_intensity": {"score": "Moderate", "confidence": "medium"},
            "tacit_coordination": {
                "score": "Moderate",
                "confidence": "medium",
                "programmatic_signals_count": 0,
                "programmatic_likelihood": "Low"
            },
            "industry_leader": {
                "score": "No clear leader",
                "confidence": "medium",
                "identified_leader": None
            },
            "demand_variability": {"score": "Moderate", "confidence": "medium", "programmatic_anchor": "Moderate"},
            "fixed_cost_level": {"score": "Moderate", "confidence": "medium", "programmatic_anchor": "Moderate"},
            "firm_similarity": {"score": "Moderate", "confidence": "medium", "programmatic_anchor": "Moderate"},
            "industry_growth": {
                "score": "Moderate",
                "confidence": "medium",
                "programmatic_anchor": "Moderate",
                "universe_cagr_3yr": None
            },
            "overall_rivalry_intensity": "Moderate",
            "industry_leader_ticker": None,
            "focal_is_leader": False,
            "low_confidence_forces": [],
            "override_flags": [],
            "data_quality_flags": []
        },
        "output": ""
    }

    def __init__(self, config: dict, llm_client: BaseLLMClient, session: dict):
        """
        Calls super().__init__("F06", config, llm_client)
        Stores session dict
        Initialises FinancialCalculator
        Initialises QualitativeScorer
        """
        super().__init__("F06", config, llm_client)
        self.session = session
        self.financial_calc = FinancialCalculator()
        self.scorer = QualitativeScorer()
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
            "cogs": ["cost of goods sold", "cost of materials consumed", "cost of revenue", "direct costs", "cost of services"],
            "net_fixed_assets": ["net fixed assets", "property plant and equipment", "net block", "tangible assets", "fixed assets net"],
            "capex": ["capital expenditure", "capex", "purchase of fixed assets", "additions to fixed assets"],
            "ebitda": ["ebitda", "operating ebitda"]
        }

    def load_broker_findings(self, broker: Any) -> dict:
        """
        Reads F02, F03, F04, F05 findings from broker.
        """
        results = {"F02": {}, "F03": {}, "F04": {}, "F05": {}}
        try:
            findings = broker.read_many(["F02", "F03", "F04", "F05"])
            f02 = findings.get("F02", {})
            f03 = findings.get("F03", {})
            f04 = findings.get("F04", {})
            f05 = findings.get("F05", {})
            
            if not f02:
                logger.warning("F02 findings missing from broker")
            if not f03:
                logger.warning("F03 findings missing from broker")
            if not f04:
                logger.warning("F04 findings missing from broker")
            if not f05:
                logger.warning("F05 findings missing from broker")
                
            results["F02"] = f02
            results["F03"] = f03
            results["F04"] = f04
            results["F05"] = f05
        except Exception as e:
            logger.warning(f"Failed to read broker findings: {e}")
            
        return results

    def run_calculations(self, context_package: dict, broker_findings: dict) -> dict:
        """
        Runs all F06-specific calculations.
        """
        fins = context_package.get("financials", {})
        focal_yearly_master = fins.get("yearly", {})
        peer_financials = fins.get("peers", {})
        focal_ticker = self.config.get("run", {}).get("focal_company", "Unknown")
        
        # STEP 1: revenue volatility
        rev_vol = self.financial_calc.compute_revenue_volatility(focal_ticker, focal_yearly_master, peer_financials, self.metric_map)
        
        # STEP 2: industry growth
        ind_growth = self.financial_calc.compute_industry_growth(focal_ticker, focal_yearly_master, peer_financials, self.metric_map)
        
        # STEP 3: firm similarity
        firm_sim = self.financial_calc.compute_firm_similarity(focal_ticker, focal_yearly_master, peer_financials, self.metric_map)
        
        # Reconstruct concentration_metrics from F03 if missing. We only really need latest_hhi for tacit signals.
        f03 = broker_findings.get("F03", {})
        latest_hhi = f03.get("latest_hhi")
        if latest_hhi is not None:
            conc_metrics = {"latest_hhi": latest_hhi}
        else:
            pms = self.financial_calc.compute_proxy_market_share(focal_ticker, focal_yearly_master, peer_financials, self.metric_map)
            conc_metrics = self.financial_calc.compute_concentration_metrics(pms)
            
        # STEP 4: tacit coordination signals
        tacit_sigs = self.financial_calc.compute_tacit_coordination_signals(focal_ticker, focal_yearly_master, peer_financials, self.metric_map, conc_metrics, firm_sim)
        
        # Adjust tacit signals for demand variability stability signal
        dv = rev_vol.get("industry_demand_variability", "Unknown")
        if dv == "Low":
            tacit_sigs["stability_signal"] = True
            tacit_sigs["signals_summary"].append("Low demand variability (highly predictable environment)")
            
        final_count = tacit_sigs.get("signals_count", 0) + (1 if tacit_sigs.get("stability_signal") else 0)
        tacit_sigs["signals_count"] = final_count
        
        if final_count == 4:
            tacit_sigs["coordination_likelihood"] = "High"
        elif final_count >= 2:
            tacit_sigs["coordination_likelihood"] = "Moderate"
        else:
            tacit_sigs["coordination_likelihood"] = "Low"
            
        # STEP 5: identify industry leader
        leader_ticker = None
        focal_is_leader = False
        
        pms_latest = f03.get("proxy_market_share_latest", {})
        if pms_latest:
            # find max share
            max_share = -1
            for comp, share in pms_latest.items():
                if share > max_share:
                    max_share = share
                    leader_ticker = comp
        else:
            pms = self.financial_calc.compute_proxy_market_share(focal_ticker, focal_yearly_master, peer_financials, self.metric_map)
            fys = sorted([k for k in pms.keys() if k != "methodology_note"], reverse=True)
            if fys:
                latest_fy = fys[0]
                fy_data = pms[latest_fy]
                max_share = -1
                for k, v in fy_data.items():
                    if k not in ["universe_revenue", "companies_included"]:
                        share = v.get("market_share_pct", 0)
                        if share > max_share:
                            max_share = share
                            leader_ticker = k
                            
        if leader_ticker == focal_ticker:
            focal_is_leader = True
            
        # STEP 6: compile programmatic anchors
        f05 = broker_findings.get("F05", {})
        fixed_cost_anchor = f05.get("asset_specificity", {}).get("score", "Moderate")
        
        return {
            "demand_variability_anchor": dv,
            "fixed_cost_anchor": fixed_cost_anchor,
            "firm_similarity_anchor": firm_sim.get("overall_firm_similarity", "Moderate"),
            "industry_growth_anchor": ind_growth.get("industry_growth_classification", "Moderate"),
            "coordination_likelihood": tacit_sigs.get("coordination_likelihood", "Low"),
            "coordination_signals_count": final_count,
            "industry_leader_ticker": leader_ticker,
            "focal_is_leader": focal_is_leader,
            
            # extra data needed for prompt
            "revenue_volatility_data": rev_vol,
            "industry_growth_data": ind_growth,
            "firm_similarity_data": firm_sim,
            "tacit_coordination_data": tacit_sigs
        }

    def build_prompt(self, context_package: dict, calculations: dict, broker_findings: dict) -> str:
        """
        Loads f06_prompt.txt template. Injects data.
        """
        base_dir = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        prompt_path = base_dir / "templates" / "prompts" / "f06_prompt.txt"
        
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                template = f.read()
        except FileNotFoundError:
            template = "{company_name}\n{prior_findings_table}\n{programmatic_anchors_table}\n{industry_growth_table}\n{firm_similarity_table}\n{coordination_signals_table}\n{industry_leader_section}\n{scoring_rubrics}\n{narrative_chunks}\n{peer_narrative_chunks}"
            
        focal_company = self.config.get("run", {}).get("focal_company", "Unknown")
        peer_set = self.config.get("run", {}).get("peer_comps", [])
        peer_set_str = ", ".join(peer_set) if peer_set else "None"
        
        f03 = broker_findings.get("F03", {})
        f04 = broker_findings.get("F04", {})
        f05 = broker_findings.get("F05", {})
        
        prior_findings_table = f"""Metric                  | Value  | Source
Supplier Power          | {f04.get('supplier_power', {}).get('score', '-')}  | F04
Buyer Power             | {f04.get('buyer_power', {}).get('score', '-')}  | F04
Barriers to Entry       | {f05.get('barriers_to_entry', {}).get('score', '-')}  | F05
Overall Entry Threat    | {f05.get('overall_entry_threat', '-')}  | F05
Industry Structure      | {f03.get('industry_structure', '-')}  | F03
Latest HHI              | {f03.get('latest_hhi', '-')}  | F03
Focal Market Share      | {f03.get('focal_market_share_latest', '-')}% | F03
Focal Rank              | {f03.get('focal_rank_latest', '-')}  | F03"""

        programmatic_anchors_table = f"""Dimension              | Anchor | Signal
Demand Variability     | {calculations.get('demand_variability_anchor', '-')}  | computed
Fixed Cost Level       | {calculations.get('fixed_cost_anchor', '-')}  | from F05 proxy
Firm Similarity        | {calculations.get('firm_similarity_anchor', '-')}  | computed
Industry Growth (3yr)  | {calculations.get('industry_growth_anchor', '-')}  | computed
Coordination Signals   | {calculations.get('coordination_signals_count', '-')}/4| {calculations.get('coordination_likelihood', '-')}"""

        ig = calculations.get("industry_growth_data", {})
        industry_growth_table = f"""Period     | Universe CAGR | Focal CAGR | Focal vs Industry
3-year     | {ig.get('universe_cagr_3yr', '-')}%        | {ig.get('focal_cagr_3yr', '-')}%     | {ig.get('focal_growth_vs_industry', '-')}
5-year     | {ig.get('universe_cagr_5yr', '-')}%        | -          | -
Full period| {ig.get('universe_cagr_full', '-')}%       | -          | -"""

        fs = calculations.get("firm_similarity_data", {})
        firm_similarity_table = f"""Dimension       | CoV    | Similarity
Revenue Size    | {fs.get('cov_revenue', '-')}  | {fs.get('revenue_similarity', '-')}
EBITDA Margin   | {fs.get('cov_margin', '-')}  | {fs.get('margin_similarity', '-')}
Capex Intensity | {fs.get('cov_capex', '-')}  | {fs.get('capex_similarity', '-')}
Overall         | -      | {fs.get('overall_firm_similarity', '-')}"""

        tc = calculations.get("tacit_coordination_data", {})
        coordination_signals_table = f"""Signal                     | Present | Value
Margin convergence         | {'Yes' if tc.get('margin_convergence_score', 0) >= 0.6 else 'No'}   | {round(tc.get('margin_convergence_score', 0) * 100, 2)}%
HHI concentration          | {'Yes' if tc.get('strong_structure_signal') else 'No'}   | > 2500
Firm similarity            | {'Yes' if tc.get('similarity_signal') else 'No'}   | High
Low demand variability     | {'Yes' if tc.get('stability_signal') else 'No'}   | Low
Signals firing             | {calculations.get('coordination_signals_count')}/4   | {tc.get('coordination_likelihood', '-')}"""

        industry_leader_section = f"""Identified leader: {calculations.get('industry_leader_ticker', 'Unknown')}
Focal is leader: {'Yes' if calculations.get('focal_is_leader') else 'No'}"""

        scoring_rubrics = ""
        for force, levels in self.scorer.F06_RUBRICS.items():
            scoring_rubrics += f"\n### {force.replace('_', ' ').title()} Rubric\n"
            for level, items in levels.items():
                scoring_rubrics += f"- **{level}**: {'; '.join(items)}\n"
                
        narrative_chunks = ""
        for chunk in context_package.get("narrative", []):
            tags = chunk.get("tags", [])
            if any(t in tags for t in ["competition", "strategy", "financials", "capex"]):
                narrative_chunks += f"\n- {chunk.get('text', '')}"
                
        if not narrative_chunks:
            narrative_chunks = "No relevant narrative chunks found."
            
        peer_narrative_chunks = ""
        for chunk in context_package.get("peer_narrative", []):
            tags = chunk.get("tags", [])
            if any(t in tags for t in ["competition", "strategy", "financials", "capex"]):
                peer_narrative_chunks += f"\n- [{chunk.get('company', 'Unknown')}] {chunk.get('text', '')}"
                
        if not peer_narrative_chunks:
            peer_narrative_chunks = "No relevant peer narrative chunks found."
            
        start_year = "FY2015"
        end_year = "FY2025"

        prompt = template.replace("{company_name}", focal_company)
        prompt = prompt.replace("{peer_set}", peer_set_str)
        prompt = prompt.replace("{start_year}", start_year)
        prompt = prompt.replace("{end_year}", end_year)
        prompt = prompt.replace("{prior_findings_table}", prior_findings_table)
        prompt = prompt.replace("{programmatic_anchors_table}", programmatic_anchors_table)
        prompt = prompt.replace("{industry_growth_table}", industry_growth_table)
        prompt = prompt.replace("{firm_similarity_table}", firm_similarity_table)
        prompt = prompt.replace("{coordination_signals_table}", coordination_signals_table)
        prompt = prompt.replace("{industry_leader_section}", industry_leader_section)
        prompt = prompt.replace("{scoring_rubrics}", scoring_rubrics)
        prompt = prompt.replace("{narrative_chunks}", narrative_chunks)
        prompt = prompt.replace("{peer_narrative_chunks}", peer_narrative_chunks)
        
        return prompt

    def parse_llm_output(self, llm_response: str, calculations: dict, broker_findings: dict) -> Tuple[dict, str]:
        """
        Parses JSON score blocks and markdown narrative.
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

        data_quality_flags = []
        override_flags = []
        scores = {}
        
        # STEP 1: Extract JSON
        json_start = llm_response.find("```json")
        json_end = llm_response.find("```", json_start + 7)
        
        if json_start != -1 and json_end != -1:
            json_str = llm_response[json_start + 7:json_end].strip()
            try:
                scores = json.loads(json_str)
            except Exception as e:
                logger.error(f"F06 JSON score block parsing failed: {e}")
                data_quality_flags.append(f"F06 JSON score block parsing failed: {e}")
        else:
            logger.error("F06 JSON score block missing from LLM response")
            data_quality_flags.append("F06 JSON score block missing from LLM response")
            
        default_block = {"score": "Moderate", "confidence": "low", "primary_evidence": {"document": "N/A", "excerpt": "N/A", "year": "N/A"}, "supporting_evidence": [], "contradicting_evidence": None, "quantitative_anchor": None}
        if not scores:
            scores = {
                "rivalry_intensity": default_block.copy(),
                "tacit_coordination": default_block.copy(),
                "industry_leader": default_block.copy(),
                "demand_variability": default_block.copy(),
                "fixed_cost_level": default_block.copy(),
                "firm_similarity": default_block.copy(),
                "industry_growth": default_block.copy()
            }
            scores["tacit_coordination"]["identified_leader_ticker"] = None
            scores["industry_leader"]["identified_leader_ticker"] = None
            scores["industry_leader"]["score"] = "No clear leader"
            
        # STEP 1: validate_all_scores
        # Again, some rubrics use different scales than High/Moderate/Low 
        # (e.g. industry_growth has Declining, industry_leader has Yes/No).
        # We will run validate, catch errors in flags, but preserve the scores.
        all_valid, val_report = self.scorer.validate_all_scores(scores)
        if not all_valid:
            for force, report in val_report.items():
                if not report["valid"]:
                    for err in report["errors"]:
                        logger.warning(f"F06 Validation error in {force}: {err}")
                        data_quality_flags.append(f"Validation error in {force}: {err}")
                        
        # STEP 2: Divergences
        dv_anchor = calculations.get("demand_variability_anchor")
        if scores.get("demand_variability", {}).get("score") != dv_anchor:
            override_flags.append(f"Demand variability LLM score ({scores.get('demand_variability', {}).get('score')}) diverges from programmatic proxy ({dv_anchor}).")
            
        fc_anchor = calculations.get("fixed_cost_anchor")
        if scores.get("fixed_cost_level", {}).get("score") != fc_anchor:
            override_flags.append(f"Fixed cost level LLM score ({scores.get('fixed_cost_level', {}).get('score')}) diverges from programmatic proxy ({fc_anchor}).")
            
        fs_anchor = calculations.get("firm_similarity_anchor")
        if scores.get("firm_similarity", {}).get("score") != fs_anchor:
            override_flags.append(f"Firm similarity LLM score ({scores.get('firm_similarity', {}).get('score')}) diverges from programmatic proxy ({fs_anchor}).")
            
        ig_anchor = calculations.get("industry_growth_anchor")
        if scores.get("industry_growth", {}).get("score") != ig_anchor:
            override_flags.append(f"Industry growth LLM score ({scores.get('industry_growth', {}).get('score')}) diverges from programmatic proxy ({ig_anchor}).")
            
        # STEP 3: Modifiers for overall_rivalry_intensity
        ri = scores.get("rivalry_intensity", {}).get("score", "Moderate")
        tc = scores.get("tacit_coordination", {}).get("score", "Moderate")
        ig = scores.get("industry_growth", {}).get("score", "Moderate")
        fc = scores.get("fixed_cost_level", {}).get("score", "Moderate")
        dv = scores.get("demand_variability", {}).get("score", "Moderate")
        
        # MODIFIER 1
        if tc == "High" and ig in ["High", "Moderate"]:
            if ri == "High": ri = "Moderate"
            elif ri == "Moderate": ri = "Low"
            
        # MODIFIER 2
        if fc == "High" and dv == "High":
            if ri == "Low": ri = "Moderate"
            elif ri == "Moderate": ri = "High"
            
        # MODIFIER 3
        if ig == "Declining":
            ri = "High"
            
        # STEP 4: Industry leader ticker
        leader_llm = scores.get("industry_leader", {}).get("identified_leader_ticker")
        leader_prog = calculations.get("industry_leader_ticker")
        if leader_llm != leader_prog:
            override_flags.append(f"LLM identified leader ({leader_llm}) diverges from programmatic leader ({leader_prog}).")
            
        # STEP 5: Confidence Flags
        confidence_flags = self.scorer.generate_confidence_flags(scores, "F06")
        
        focal_company = self.config.get("run", {}).get("focal_company", "Unknown")
        base_dir = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        processed_dir = self.config.get("paths", {}).get("processed_dir", "processed")
        out_dir = base_dir / processed_dir / focal_company / "frameworks"
        out_dir.mkdir(parents=True, exist_ok=True)
        
        if confidence_flags:
            with open(out_dir / "F06_confidence_flags.json", "w", encoding="utf-8") as f:
                json.dump(confidence_flags, f, indent=2)
                
            appendix = self.scorer.format_appendix_recommendations(confidence_flags, focal_company)
            with open(out_dir / "F06_appendix_recommendations.md", "w", encoding="utf-8") as f:
                f.write(appendix)
                
        # STEP 6: Extract Narrative
        narrative = llm_response[json_end + 3:].strip() if json_end != -1 else llm_response
        
        # STEP 7: Validate Narrative Sections
        required_sections = [
            "## Rivalry Overview",
            "## Tacit Coordination Assessment",
            "## Industry Leadership",
            "## Demand & Cost Structure",
            "## Firm Similarity & Incentive Alignment",
            "## Industry Growth Context",
            "## Summary"
        ]
        
        for section in required_sections:
            if section not in narrative:
                logger.warning(f"F06 LLM narrative missing section: {section}")
                narrative += f"\n\n{section}\n*Analysis unavailable for this section.*"
                
        # Apply word limit
        words = narrative.split()
        if len(words) > 1000:
            logger.info(f"F06 LLM output trimmed from {len(words)} to 1000 words")
            trimmed = " ".join(words[:1000])
            last_period = trimmed.rfind(".")
            if last_period != -1:
                narrative = trimmed[:last_period+1]
            else:
                narrative = trimmed
                
        # Append confidence warnings
        warnings_md = self.scorer.format_confidence_warnings(confidence_flags)
        if warnings_md:
            narrative += f"\n\n{warnings_md}"
            
        ig_data = calculations.get("industry_growth_data", {})
        
        findings = {
            "rivalry_intensity": {
                "score": scores.get("rivalry_intensity", {}).get("score", "Moderate"),
                "confidence": scores.get("rivalry_intensity", {}).get("confidence", "low")
            },
            "tacit_coordination": {
                "score": scores.get("tacit_coordination", {}).get("score", "Moderate"),
                "confidence": scores.get("tacit_coordination", {}).get("confidence", "low"),
                "programmatic_signals_count": calculations.get("coordination_signals_count", 0),
                "programmatic_likelihood": calculations.get("coordination_likelihood", "Low")
            },
            "industry_leader": {
                "score": scores.get("industry_leader", {}).get("score", "No clear leader"),
                "confidence": scores.get("industry_leader", {}).get("confidence", "low"),
                "identified_leader": leader_llm if leader_llm else leader_prog
            },
            "demand_variability": {
                "score": scores.get("demand_variability", {}).get("score", "Moderate"),
                "confidence": scores.get("demand_variability", {}).get("confidence", "low"),
                "programmatic_anchor": dv_anchor
            },
            "fixed_cost_level": {
                "score": scores.get("fixed_cost_level", {}).get("score", "Moderate"),
                "confidence": scores.get("fixed_cost_level", {}).get("confidence", "low"),
                "programmatic_anchor": fc_anchor
            },
            "firm_similarity": {
                "score": scores.get("firm_similarity", {}).get("score", "Moderate"),
                "confidence": scores.get("firm_similarity", {}).get("confidence", "low"),
                "programmatic_anchor": fs_anchor
            },
            "industry_growth": {
                "score": scores.get("industry_growth", {}).get("score", "Moderate"),
                "confidence": scores.get("industry_growth", {}).get("confidence", "low"),
                "programmatic_anchor": ig_anchor,
                "universe_cagr_3yr": ig_data.get("universe_cagr_3yr")
            },
            "overall_rivalry_intensity": ri,
            "industry_leader_ticker": leader_prog,
            "focal_is_leader": calculations.get("focal_is_leader", False),
            "low_confidence_forces": [f["force"] for f in confidence_flags],
            "override_flags": override_flags,
            "data_quality_flags": data_quality_flags
        }
        
        return findings, narrative, key_finding

    def run(self, context_package: dict, broker: Any = None) -> dict:
        """
        Master run method.
        """
        try:
            broker_findings = self.load_broker_findings(broker) if broker else {}
            calculations = self.run_calculations(context_package, broker_findings)
            prompt = self.build_prompt(context_package, calculations, broker_findings)
            
            system_prompt = "You are a senior equity research analyst."
                
            llm_response = ""
            if self.llm_client:
                llm_response = self.llm_client.complete(system_prompt, prompt)
            else:
                llm_response = "```json\n{}\n```\n## Rivalry Overview\nTest\n## Tacit Coordination Assessment\nTest\n## Industry Leadership\nTest\n## Demand & Cost Structure\nTest\n## Firm Similarity & Incentive Alignment\nTest\n## Industry Growth Context\nTest\n## Summary\nTest."
                
            findings, narrative, key_finding = self.parse_llm_output(llm_response, calculations, broker_findings)
            
            result = self.HARDCODED_OUTPUT_SCHEMA.copy()
            result["key_finding"] = key_finding
            result["status"] = "success"
            result["findings"] = findings
            result["output"] = narrative
            
            self.save_output(result)
            
            if broker:
                broker.write("F06", result["findings"])
                
            return result
        except Exception as e:
            logger.error(f"F06 run error: {e}", exc_info=True)
            failed = self.HARDCODED_OUTPUT_SCHEMA.copy()
            failed["status"] = "failed"
            failed["error"] = str(e)
            
            self.save_output(failed)
            
            if broker:
                broker.write("F06", {})
                
            return failed
