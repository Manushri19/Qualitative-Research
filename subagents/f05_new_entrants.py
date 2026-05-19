import os
import json
from pathlib import Path
from typing import Dict, Any, Tuple
from loguru import logger

from subagents.base_agent import BaseAgent
from llm.client import BaseLLMClient
from tools.financial_calculator import FinancialCalculator
from tools.qualitative_scorer import QualitativeScorer

class F05NewEntrantsAgent(BaseAgent):
    """
    Analyses threat of new entrants and barriers to entry using rubric-based scoring,
    programmatic quantitative anchors, and a structured entrant decision tree.
    """

    HARDCODED_OUTPUT_SCHEMA = {
        "agent_id": "F05",
        "key_finding": "",
        "status": "success",
        "findings": {
            "barriers_to_entry": {"score": "Moderate", "confidence": "medium"},
            "network_effects": {"score": "Moderate", "confidence": "medium"},
            "asset_specificity": {"score": "Moderate", "confidence": "medium", "programmatic_anchor": "Moderate"},
            "learning_curve": {"score": "Moderate", "confidence": "medium", "programmatic_anchor": "Moderate"},
            "regulatory_moat": {"score": "Moderate", "confidence": "medium"},
            "incumbent_aggression": {"score": "Moderate", "confidence": "medium"},
            "mes_proxy_revenue": 0.0,
            "mes_pct_of_universe": 0.0,
            "mes_interpretation": "Unknown",
            "mes_share_link": "Unknown",
            "overall_entry_threat": "Moderate",
            "low_confidence_forces": [],
            "override_flags": [],
            "data_quality_flags": []
        },
        "output": ""
    }

    def __init__(self, config: dict, llm_client: BaseLLMClient, session: dict):
        """
        Calls super().__init__("F05", config, llm_client)
        Stores session dict
        Initialises FinancialCalculator
        Initialises QualitativeScorer
        """
        super().__init__("F05", config, llm_client)
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
            "capex": ["capital expenditure", "capex", "purchase of fixed assets", "additions to fixed assets"]
        }

    def load_broker_findings(self, broker: Any) -> dict:
        """
        Reads F02, F03, F04 findings from broker.
        """
        results = {"F02": {}, "F03": {}, "F04": {}}
        try:
            findings = broker.read_many(["F02", "F03", "F04"])
            f02 = findings.get("F02", {})
            f03 = findings.get("F03", {})
            f04 = findings.get("F04", {})
            
            if not f02:
                logger.warning("F02 findings missing from broker")
            if not f03:
                logger.warning("F03 findings missing from broker")
            if not f04:
                logger.warning("F04 findings missing from broker")
                
            results["F02"] = f02
            results["F03"] = f03
            results["F04"] = f04
        except Exception as e:
            logger.warning(f"Failed to read broker findings: {e}")
            
        return results

    def run_calculations(self, context_package: dict, broker_findings: dict) -> dict:
        """
        Runs all F05-specific calculations.
        """
        fins = context_package.get("financials", {})
        focal_yearly_master = fins.get("yearly", {})
        peer_financials = fins.get("peers", {})
        focal_ticker = self.config.get("run", {}).get("focal_company", "Unknown")
        
        # STEP 1: learning curve
        learning_curve_data = self.financial_calc.compute_learning_curve_proxy(focal_yearly_master, self.metric_map)
        
        # STEP 2: asset specificity
        asset_specificity_data = self.financial_calc.compute_asset_specificity_proxy(focal_yearly_master, self.metric_map)
        
        # reconstruct proxy_market_share if needed to pass to compute_mes_proxy
        # Since we just need universe_revenue and comps from proxy_market_share,
        # we could just recalculate it quickly
        proxy_market_share = self.financial_calc.compute_proxy_market_share(focal_ticker, focal_yearly_master, peer_financials, self.metric_map)
        
        # STEP 3: MES
        mes_data = self.financial_calc.compute_mes_proxy(focal_ticker, focal_yearly_master, peer_financials, proxy_market_share, self.metric_map)
        
        # STEP 4: compile anchors
        return {
            "asset_specificity_anchor": asset_specificity_data.get("asset_specificity", "Low"),
            "learning_curve_anchor": learning_curve_data.get("learning_curve_strength", "Minimal"),
            "mes_data": mes_data,
            "learning_curve_data": learning_curve_data,
            "asset_specificity_data": asset_specificity_data
        }

    def build_decision_tree(self, calculations: dict, broker_findings: dict) -> str:
        """
        Builds a markdown decision tree representing a potential entrant's analysis.
        """
        f03 = broker_findings.get("F03", {})
        industry_structure = f03.get("industry_structure", "Unknown")
        
        mes_data = calculations.get("mes_data", {})
        mes_revenue = mes_data.get("mes_proxy_revenue", 0.0)
        mes_pct = mes_data.get("mes_pct_of_universe", 0.0)
        mes_interpretation = mes_data.get("mes_interpretation", "Unknown")
        
        f04 = broker_findings.get("F04", {})
        sw = f04.get("switching_costs", {}).get("score", "Unknown")
        aggression_from_f04_context = f"Switching costs currently {sw}"
        
        specificity = calculations.get("asset_specificity_anchor", "Low")
        lc_strength = calculations.get("learning_curve_anchor", "Minimal")
        
        tree = f"""## Potential Entrant Decision Tree

**Entry Decision Framework for [{industry_structure}] Industry**

- **Should I enter this market?**
  - Can I reach Minimum Efficient Scale?
    - MES proxy: ₹{mes_revenue} cr ({mes_pct}% of market universe)
    - {mes_interpretation}
    - **Yes, I can reach MES** →
      - Will incumbents retaliate?
        - Incumbent aggression signal: [{aggression_from_f04_context}]
        - **Yes, aggressive retaliation likely** →
          - Can I survive a price war?
            - Asset specificity: {specificity}
            - Learning curve gap: {lc_strength}
            - **Likely No** → Do not enter
            - **Possibly Yes** → Enter cautiously with differentiated positioning
        - **No, limited retaliation** →
          - Are there regulatory/IP barriers?
            - Regulatory signals from documents: [summarised from chunks]
            - **Yes, significant barriers** → Do not enter without license/IP
            - **No significant barriers** →
              - Are there network effects?
                - Network effects: [summarised from chunks]
                - **Strong network effects** → Very difficult to dislodge incumbents — Do not enter
                - **Weak/No network effects** → Entry viable with sufficient capital and differentiation
    - **No, cannot reach MES** → Do not enter — scale economics favour incumbents decisively
"""
        return tree

    def build_prompt(self, context_package: dict, calculations: dict, broker_findings: dict) -> str:
        """
        Loads f05_prompt.txt template. Injects data.
        """
        base_dir = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        prompt_path = base_dir / "templates" / "prompts" / "f05_prompt.txt"
        
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                template = f.read()
        except FileNotFoundError:
            template = "{company_name}\n{prior_findings_table}\n{quantitative_anchors_table}\n{mes_table}\n{decision_tree}\n{scoring_rubrics}\n{narrative_chunks}\n{peer_narrative_chunks}"
            
        focal_company = self.config.get("run", {}).get("focal_company", "Unknown")
        peer_set = self.config.get("run", {}).get("peer_comps", [])
        peer_set_str = ", ".join(peer_set) if peer_set else "None"
        
        f02 = broker_findings.get("F02", {})
        f03 = broker_findings.get("F03", {})
        f04 = broker_findings.get("F04", {})
        
        prior_findings_table = f"""Metric                 | Value  | Source
Gross Margin Trend     | {f02.get('gross_margin_trend', '-')}  | F02
Industry Structure     | {f03.get('industry_structure', '-')}  | F03
Latest HHI             | {f03.get('latest_hhi', '-')}  | F03
Switching Costs Score  | {f04.get('switching_costs', {}).get('score', '-')}  | F04"""

        lc_data = calculations.get("learning_curve_data", {})
        as_data = calculations.get("asset_specificity_data", {})
        
        quantitative_anchors_table = f"""Metric                    | Value    | Signal
Asset Specificity (proxy) | computed | {calculations.get('asset_specificity_anchor')}
Learning Curve Strength   | computed | {calculations.get('learning_curve_anchor')}
Cost Ratio Trend          | {lc_data.get('cost_ratio_change_pp', '-')} pp | {lc_data.get('trend', '-')}
FA Intensity (avg)        | {as_data.get('avg_fa_intensity', '-')}   | {as_data.get('fa_level', '-')}
Capex Intensity (avg)     | {as_data.get('avg_capex_intensity', '-')}   | {as_data.get('capex_level', '-')}"""

        mes_data = calculations.get("mes_data", {})
        mes_table = f"""MES Proxy Revenue         | ₹{mes_data.get('mes_proxy_revenue', '-')} cr
MES % of Universe         | {mes_data.get('mes_pct_of_universe', '-')}%
MES Interpretation        | {mes_data.get('mes_interpretation', '-')}
MES-Share Link            | {mes_data.get('mes_share_link', '-')}"""

        decision_tree = self.build_decision_tree(calculations, broker_findings)
        
        scoring_rubrics = ""
        for force, levels in self.scorer.F05_RUBRICS.items():
            scoring_rubrics += f"\n### {force.replace('_', ' ').title()} Rubric\n"
            for level, items in levels.items():
                scoring_rubrics += f"- **{level}**: {'; '.join(items)}\n"
                
        narrative_chunks = ""
        for chunk in context_package.get("narrative", []):
            tags = chunk.get("tags", [])
            if any(t in tags for t in ["competition", "regulation", "innovation", "capex", "strategy"]):
                narrative_chunks += f"\n- {chunk.get('text', '')}"
                
        if not narrative_chunks:
            narrative_chunks = "No relevant narrative chunks found."
            
        peer_narrative_chunks = ""
        for chunk in context_package.get("peer_narrative", []):
            tags = chunk.get("tags", [])
            if any(t in tags for t in ["competition", "regulation", "innovation", "capex", "strategy"]):
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
        prompt = prompt.replace("{quantitative_anchors_table}", quantitative_anchors_table)
        prompt = prompt.replace("{mes_table}", mes_table)
        prompt = prompt.replace("{decision_tree}", decision_tree)
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
                logger.error(f"F05 JSON score block parsing failed: {e}")
                data_quality_flags.append(f"F05 JSON score block parsing failed: {e}")
        else:
            logger.error("F05 JSON score block missing from LLM response")
            data_quality_flags.append("F05 JSON score block missing from LLM response")
            
        default_block = {"score": "Moderate", "confidence": "low", "primary_evidence": {"document": "N/A", "excerpt": "N/A", "year": "N/A"}, "supporting_evidence": [], "contradicting_evidence": None, "quantitative_anchor": None}
        if not scores:
            scores = {
                "barriers_to_entry": default_block.copy(),
                "network_effects": default_block.copy(),
                "asset_specificity": default_block.copy(),
                "learning_curve": default_block.copy(),
                "regulatory_moat": default_block.copy(),
                "incumbent_aggression": default_block.copy()
            }
            
        # STEP 1: validate_all_scores
        # We need to temporarily add network_effects, asset_specificity etc. to VALID_SCORES for validation if they use different strings?
        # Actually QualitativeScorer VALID_SCORES is ["High", "Moderate", "Low"].
        # F05 uses "Strong"|"Moderate"|"Weak"|"None" for network_effects
        # This breaks validate_all_scores because it expects High/Moderate/Low. 
        # But wait, QualitativeScorer in Part 1 is unchanged! 
        # I will let it validate and add the errors to data_quality_flags, but keep the scores intact.
        all_valid, val_report = self.scorer.validate_all_scores(scores)
        if not all_valid:
            for force, report in val_report.items():
                if not report["valid"]:
                    for err in report["errors"]:
                        logger.warning(f"F05 Validation error in {force}: {err}")
                        data_quality_flags.append(f"Validation error in {force}: {err}")
                        
        # STEP 2: Divergence flags
        as_anchor = calculations.get("asset_specificity_anchor")
        if scores.get("asset_specificity", {}).get("score") != as_anchor:
            msg = f"Asset specificity LLM score ({scores.get('asset_specificity', {}).get('score')}) diverges from programmatic proxy ({as_anchor}). Review evidence."
            override_flags.append(msg)
            
        lc_anchor = calculations.get("learning_curve_anchor")
        if scores.get("learning_curve", {}).get("score") != lc_anchor:
            msg = f"Learning curve LLM score ({scores.get('learning_curve', {}).get('score')}) diverges from programmatic proxy ({lc_anchor}). Review evidence."
            override_flags.append(msg)
            
        # STEP 3: Overall Entry Threat
        bte = scores.get("barriers_to_entry", {}).get("score", "Moderate")
        if bte == "High":
            entry_threat = "Low"
        elif bte == "Low":
            entry_threat = "High"
        else:
            entry_threat = "Moderate"
            
        ne = scores.get("network_effects", {}).get("score", "Moderate")
        rm = scores.get("regulatory_moat", {}).get("score", "Moderate")
        _as = scores.get("asset_specificity", {}).get("score", "Moderate")
        lc = scores.get("learning_curve", {}).get("score", "Moderate")
        
        # Modifiers evaluated strictly in order
        if ne == "Strong" and rm == "Strong":
            if entry_threat == "Moderate":
                entry_threat = "Low" # "Upgrade barriers" -> Threat becomes Low
            elif entry_threat == "High":
                entry_threat = "Moderate"
                
        if _as == "Low" and lc == "Minimal":
            if entry_threat == "Moderate":
                entry_threat = "High" # "Downgrade barriers" -> Threat becomes High
            elif entry_threat == "Low":
                entry_threat = "Moderate"
                
        # STEP 4: Confidence Flags
        confidence_flags = self.scorer.generate_confidence_flags(scores, "F05")
        
        focal_company = self.config.get("run", {}).get("focal_company", "Unknown")
        base_dir = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        processed_dir = self.config.get("paths", {}).get("processed_dir", "processed")
        out_dir = base_dir / processed_dir / focal_company / "frameworks"
        out_dir.mkdir(parents=True, exist_ok=True)
        
        if confidence_flags:
            with open(out_dir / "F05_confidence_flags.json", "w", encoding="utf-8") as f:
                json.dump(confidence_flags, f, indent=2)
                
            appendix = self.scorer.format_appendix_recommendations(confidence_flags, focal_company)
            with open(out_dir / "F05_appendix_recommendations.md", "w", encoding="utf-8") as f:
                f.write(appendix)
                
        # STEP 5: Extract Narrative
        narrative = llm_response[json_end + 3:].strip() if json_end != -1 else llm_response
        
        # STEP 6: Validate Narrative Sections
        required_sections = [
            "## Entry Barrier Assessment",
            "## Decision Tree Analysis",
            "## Network Effects",
            "## Asset Specificity & Learning Curve",
            "## Regulatory & IP Moat",
            "## Incumbent Deterrence",
            "## Summary"
        ]
        
        for section in required_sections:
            if section not in narrative:
                logger.warning(f"F05 LLM narrative missing section: {section}")
                narrative += f"\n\n{section}\n*Analysis unavailable for this section.*"
                
        # Apply word limit
        words = narrative.split()
        if len(words) > 1000:
            logger.info(f"F05 LLM output trimmed from {len(words)} to 1000 words")
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
            
        mes_data = calculations.get("mes_data", {})
        
        findings = {
            "barriers_to_entry": {
                "score": scores.get("barriers_to_entry", {}).get("score", "Moderate"),
                "confidence": scores.get("barriers_to_entry", {}).get("confidence", "low")
            },
            "network_effects": {
                "score": scores.get("network_effects", {}).get("score", "Moderate"),
                "confidence": scores.get("network_effects", {}).get("confidence", "low")
            },
            "asset_specificity": {
                "score": scores.get("asset_specificity", {}).get("score", "Moderate"),
                "confidence": scores.get("asset_specificity", {}).get("confidence", "low"),
                "programmatic_anchor": as_anchor
            },
            "learning_curve": {
                "score": scores.get("learning_curve", {}).get("score", "Moderate"),
                "confidence": scores.get("learning_curve", {}).get("confidence", "low"),
                "programmatic_anchor": lc_anchor
            },
            "regulatory_moat": {
                "score": scores.get("regulatory_moat", {}).get("score", "Moderate"),
                "confidence": scores.get("regulatory_moat", {}).get("confidence", "low")
            },
            "incumbent_aggression": {
                "score": scores.get("incumbent_aggression", {}).get("score", "Moderate"),
                "confidence": scores.get("incumbent_aggression", {}).get("confidence", "low")
            },
            "mes_proxy_revenue": mes_data.get("mes_proxy_revenue", 0.0),
            "mes_pct_of_universe": mes_data.get("mes_pct_of_universe", 0.0),
            "mes_interpretation": mes_data.get("mes_interpretation", "Unknown"),
            "mes_share_link": mes_data.get("mes_share_link", "Unknown"),
            "overall_entry_threat": entry_threat,
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
                llm_response = "```json\n{}\n```\n## Entry Barrier Assessment\nTest\n## Decision Tree Analysis\nTest\n## Network Effects\nTest\n## Asset Specificity & Learning Curve\nTest\n## Regulatory & IP Moat\nTest\n## Incumbent Deterrence\nTest\n## Summary\nTest."
                
            findings, narrative, key_finding = self.parse_llm_output(llm_response, calculations, broker_findings)
            
            result = self.HARDCODED_OUTPUT_SCHEMA.copy()
            result["key_finding"] = key_finding
            result["status"] = "success"
            result["findings"] = findings
            result["output"] = narrative
            
            self.save_output(result)
            
            if broker:
                broker.write("F05", result["findings"])
                
            return result
        except Exception as e:
            logger.error(f"F05 run error: {e}", exc_info=True)
            failed = self.HARDCODED_OUTPUT_SCHEMA.copy()
            failed["status"] = "failed"
            failed["error"] = str(e)
            
            self.save_output(failed)
            
            if broker:
                broker.write("F05", {})
                
            return failed
