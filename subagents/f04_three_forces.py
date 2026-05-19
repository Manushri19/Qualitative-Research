import os
import json
from pathlib import Path
from typing import Dict, Any, Tuple
from loguru import logger

from subagents.base_agent import BaseAgent
from llm.client import BaseLLMClient
from tools.qualitative_scorer import QualitativeScorer

class F04ThreeForcesAgent(BaseAgent):
    """
    Analyses supplier power, buyer power, and substitution threat 
    using rubric-based forced scoring with structured evidence requirements.
    First purely qualitative subagent.
    """
    
    HARDCODED_OUTPUT_SCHEMA = {
        "agent_id": "F04",
        "key_finding": "",
        "status": "success",
        "findings": {
            "supplier_power": {
                "score": "Moderate",
                "confidence": "medium",
                "gross_margin_override_applied": False
            },
            "buyer_power": {
                "score": "Moderate",
                "confidence": "medium",
                "contradiction_flag": False
            },
            "substitution_threat": {
                "score": "Moderate",
                "confidence": "medium"
            },
            "switching_costs": {
                "score": "Moderate",
                "confidence": "medium"
            },
            "overall_force_pressure": "Moderate",
            "low_confidence_forces": [],
            "override_flags": [],
            "data_quality_flags": []
        },
        "output": ""
    }

    def __init__(self, config: dict, llm_client: BaseLLMClient, session: dict):
        """
        Calls super().__init__("F04", config, llm_client)
        Stores session dict
        Initialises QualitativeScorer
        """
        super().__init__("F04", config, llm_client)
        self.session = session
        self.scorer = QualitativeScorer()

    def load_broker_findings(self, broker: Any) -> dict:
        """
        Reads F02 and F03 findings from context broker.
        """
        results = {"F02": {}, "F03": {}}
        try:
            findings = broker.read_many(["F02", "F03"])
            f02 = findings.get("F02", {})
            f03 = findings.get("F03", {})
            if not f02:
                logger.warning("F02 findings missing from broker")
            if not f03:
                logger.warning("F03 findings missing from broker")
            results["F02"] = f02
            results["F03"] = f03
        except Exception as e:
            logger.warning(f"Failed to read broker findings: {e}")
        return results

    def build_prompt(self, context_package: dict, broker_findings: dict) -> str:
        """
        Loads f04_prompt.txt template. Injects data.
        """
        base_dir = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        prompt_path = base_dir / "templates" / "prompts" / "f04_prompt.txt"
        
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                template = f.read()
        except FileNotFoundError:
            template = "{company_name}\n{prior_findings_table}\n{scoring_rubrics}\n{narrative_chunks}\n{peer_narrative_chunks}"
            
        focal_company = self.config.get("run", {}).get("focal_company", "Unknown")
        peer_set = self.config.get("run", {}).get("peer_comps", [])
        peer_set_str = ", ".join(peer_set) if peer_set else "None"
        
        f02 = broker_findings.get("F02", {})
        f03 = broker_findings.get("F03", {})
        
        prior_findings_table = f"""Metric                  | Value   | Source
Gross Margin Latest     | {f02.get('gross_margin_latest', '-')}%  | F02
Gross Margin Trend      | {f02.get('gross_margin_trend', '-')}   | F02
Industry Structure      | {f03.get('industry_structure', '-')}   | F03
Industry Stability      | {f03.get('industry_share_stability', '-')}   | F03"""

        scoring_rubrics = """
### Supplier Power Rubric
- **High**: Limited supplier base, inputs are highly differentiated, switching suppliers involves significant cost/delay, suppliers forward integration is a credible threat.
- **Moderate**: Handful of viable suppliers, some input differentiation, switching is possible but involves moderate friction.
- **Low**: Commoditised inputs, numerous alternative suppliers, low switching costs, buyer backward integration is a credible threat.

### Buyer Power Rubric
- **High**: High customer concentration, low switching costs for buyers, products are undifferentiated, buyers are highly price-sensitive.
- **Moderate**: Fragmented customer base but with some large accounts, moderate switching costs, some product differentiation.
- **Low**: Highly fragmented customer base, high switching costs, highly differentiated product, buyer price sensitivity is low.

### Substitution Threat Rubric
- **High**: Cost-effective substitutes readily available, customer switching cost to substitute is low, substitute performance is improving rapidly.
- **Moderate**: Substitutes exist but involve trade-offs in performance or cost, switching involves moderate friction.
- **Low**: No viable direct substitutes, proprietary technology or network effects create strong lock-in.

### Switching Costs Rubric
- **High**: Deep integration into customer workflows, high financial penalty for breaking contracts, significant retraining required.
- **Moderate**: Some integration friction, moderate financial or temporal costs to switch.
- **Low**: Plug-and-play replacement possible, no significant financial or operational penalties.
"""

        narrative_chunks = ""
        for chunk in context_package.get("narrative", []):
            tags = chunk.get("tags", [])
            if any(t in tags for t in ["suppliers", "customers", "competition", "innovation", "strategy"]):
                narrative_chunks += f"\n- {chunk.get('text', '')}"
                
        if not narrative_chunks:
            narrative_chunks = "No relevant narrative chunks found."
            
        peer_narrative_chunks = ""
        for chunk in context_package.get("peer_narrative", []):
            tags = chunk.get("tags", [])
            if any(t in tags for t in ["suppliers", "customers", "competition", "innovation", "strategy"]):
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
        prompt = prompt.replace("{scoring_rubrics}", scoring_rubrics)
        prompt = prompt.replace("{narrative_chunks}", narrative_chunks)
        prompt = prompt.replace("{peer_narrative_chunks}", peer_narrative_chunks)
        
        return prompt

    def parse_llm_output(self, llm_response: str, broker_findings: dict) -> Tuple[dict, str]:
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
                logger.error(f"F04 JSON score block parsing failed: {e}")
                data_quality_flags.append(f"F04 JSON score block parsing failed: {e}")
        else:
            logger.error("F04 JSON score block missing from LLM response")
            data_quality_flags.append("F04 JSON score block missing from LLM response")
            
        if not scores:
            scores = {
                "supplier_power": {"score": "Moderate", "confidence": "low", "primary_evidence": {"document": "N/A", "excerpt": "N/A", "year": "N/A"}, "supporting_evidence": [], "contradicting_evidence": None, "quantitative_anchor": None},
                "buyer_power": {"score": "Moderate", "confidence": "low", "primary_evidence": {"document": "N/A", "excerpt": "N/A", "year": "N/A"}, "supporting_evidence": [], "contradicting_evidence": None, "quantitative_anchor": None},
                "substitution_threat": {"score": "Moderate", "confidence": "low", "primary_evidence": {"document": "N/A", "excerpt": "N/A", "year": "N/A"}, "supporting_evidence": [], "contradicting_evidence": None, "quantitative_anchor": None},
                "switching_costs": {"score": "Moderate", "confidence": "low", "primary_evidence": {"document": "N/A", "excerpt": "N/A", "year": "N/A"}, "supporting_evidence": [], "contradicting_evidence": None, "quantitative_anchor": None}
            }
            
        # STEP 2: Validate scores
        all_valid, val_report = self.scorer.validate_all_scores(scores)
        if not all_valid:
            for force, report in val_report.items():
                if not report["valid"]:
                    for err in report["errors"]:
                        logger.warning(f"F04 Validation error in {force}: {err}")
                        data_quality_flags.append(f"Validation error in {force}: {err}")
                    if "score" not in scores.get(force, {}):
                        scores[force] = {"score": "Moderate", "confidence": "low"}
                    else:
                        scores[force]["confidence"] = "low"
                        
        # STEP 3: Override
        gross_margin_trend = broker_findings.get("F02", {}).get("gross_margin_trend", "stable")
        scores, override_flags = self.scorer.apply_gross_margin_override(scores, gross_margin_trend)
        
        # STEP 4: Confidence Flags
        confidence_flags = self.scorer.generate_confidence_flags(scores, "F04")
        
        focal_company = self.config.get("run", {}).get("focal_company", "Unknown")
        base_dir = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        processed_dir = self.config.get("paths", {}).get("processed_dir", "processed")
        out_dir = base_dir / processed_dir / focal_company / "frameworks"
        out_dir.mkdir(parents=True, exist_ok=True)
        
        if confidence_flags:
            with open(out_dir / "F04_confidence_flags.json", "w", encoding="utf-8") as f:
                json.dump(confidence_flags, f, indent=2)
                
            appendix = self.scorer.format_appendix_recommendations(confidence_flags, focal_company)
            with open(out_dir / "F04_appendix_recommendations.md", "w", encoding="utf-8") as f:
                f.write(appendix)
                
        # STEP 5: Extract Narrative
        narrative = llm_response[json_end + 3:].strip() if json_end != -1 else llm_response
        
        # STEP 6: Validate Narrative Sections
        required_sections = [
            "## Supplier Power Analysis",
            "## Buyer Power Analysis",
            "## Substitution Threat Analysis",
            "## Switching Costs Analysis",
            "## Summary"
        ]
        
        for section in required_sections:
            if section not in narrative:
                logger.warning(f"F04 LLM narrative missing section: {section}")
                narrative += f"\n\n{section}\n*Analysis unavailable for this section.*"
                
        # Apply word limit
        words = narrative.split()
        if len(words) > 950:
            logger.info(f"F04 LLM output trimmed from {len(words)} to 950 words")
            trimmed = " ".join(words[:950])
            last_period = trimmed.rfind(".")
            if last_period != -1:
                narrative = trimmed[:last_period+1]
            else:
                narrative = trimmed
                
        # STEP 7: Append confidence warnings
        warnings_md = self.scorer.format_confidence_warnings(confidence_flags)
        if warnings_md:
            narrative += f"\n\n{warnings_md}"
            
        # STEP 8: Compute overall_force_pressure
        summary = self.scorer.compute_summary_scores(scores)
        valid_nums = [s["numeric"] for s in summary.values() if s["numeric"] > 0]
        mean_score = sum(valid_nums) / len(valid_nums) if valid_nums else 2.0
        
        if mean_score >= 2.5:
            overall_pressure = "High"
        elif mean_score >= 1.5:
            overall_pressure = "Moderate"
        else:
            overall_pressure = "Low"
            
        findings = {
            "supplier_power": {
                "score": scores.get("supplier_power", {}).get("score", "Moderate"),
                "confidence": scores.get("supplier_power", {}).get("confidence", "low"),
                "gross_margin_override_applied": any("Supplier power score upgraded" in f for f in override_flags)
            },
            "buyer_power": {
                "score": scores.get("buyer_power", {}).get("score", "Moderate"),
                "confidence": scores.get("buyer_power", {}).get("confidence", "low"),
                "contradiction_flag": any("buyer power score noted despite" in f for f in override_flags)
            },
            "substitution_threat": {
                "score": scores.get("substitution_threat", {}).get("score", "Moderate"),
                "confidence": scores.get("substitution_threat", {}).get("confidence", "low")
            },
            "switching_costs": {
                "score": scores.get("switching_costs", {}).get("score", "Moderate"),
                "confidence": scores.get("switching_costs", {}).get("confidence", "low")
            },
            "overall_force_pressure": overall_pressure,
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
            prompt = self.build_prompt(context_package, broker_findings)
            
            system_prompt = "You are a senior equity research analyst."
                
            llm_response = ""
            if self.llm_client:
                llm_response = self.llm_client.complete(system_prompt, prompt)
            else:
                llm_response = "```json\n{}\n```\n## Supplier Power Analysis\nTest\n## Buyer Power Analysis\nTest\n## Substitution Threat Analysis\nTest\n## Switching Costs Analysis\nTest\n## Summary\nTest."
                
            findings, narrative, key_finding = self.parse_llm_output(llm_response, broker_findings)
            
            result = self.HARDCODED_OUTPUT_SCHEMA.copy()
            result["key_finding"] = key_finding
            result["status"] = "success"
            result["findings"] = findings
            result["output"] = narrative
            
            self.save_output(result)
            
            if broker:
                broker.write("F04", result["findings"])
                
            return result
        except Exception as e:
            logger.error(f"F04 run error: {e}", exc_info=True)
            failed = self.HARDCODED_OUTPUT_SCHEMA.copy()
            failed["status"] = "failed"
            failed["error"] = str(e)
            
            self.save_output(failed)
            
            if broker:
                broker.write("F04", {})
                
            return failed
