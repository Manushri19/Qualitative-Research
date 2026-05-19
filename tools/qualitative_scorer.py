import os
import json
from loguru import logger

class QualitativeScorer:
    """
    Validates and post-processes LLM scoring output for qualitative framework subagents.
    Ensures scores are rubric-grounded, evidence is cited, contradictions are flagged, 
    and low confidence findings generate recommendations.
    """

    VALID_SCORES = ["High", "Moderate", "Low"]
    VALID_CONFIDENCE = ["high", "medium", "low"]

    F05_RUBRICS = {
        "barriers_to_entry": {
            "High": [
                "Capital requirements prohibitively large for new entrants",
                "Regulatory licenses or patents protect incumbents",
                "Strong network effects favour incumbents",
                "Significant learning curve advantages demonstrated",
                "Highly specific assets deter exit and entry",
                "Incumbents known to respond aggressively to entry attempts"
            ],
            "Moderate": [
                "Some capital barriers but not prohibitive",
                "Partial regulatory protection",
                "Moderate network effects present",
                "Some learning curve benefit observed",
                "Mixed asset specificity signals"
            ],
            "Low": [
                "Low capital requirements for entry",
                "No significant regulatory barriers",
                "No meaningful network effects",
                "No learning curve evidence",
                "Generic assets easily acquired",
                "Incumbents show no deterrence behaviour"
            ]
        },
        "network_effects": {
            "Strong": [
                "Product value explicitly increases with user base",
                "Platform or marketplace model present",
                "High user retention tied to network size",
                "Management explicitly references network effects as competitive advantage"
            ],
            "Moderate": [
                "Some indirect network benefits present",
                "Data network effects mentioned but limited",
                "Brand network effects present"
            ],
            "Weak": [
                "Limited network dynamics mentioned",
                "Product value largely independent of user base size"
            ],
            "None": [
                "No network effects evident in documents",
                "Standalone product with no network dynamics"
            ]
        },
        "asset_specificity": {
            "High": [
                "Fixed asset intensity > 30% of revenue",
                "Sustained high capex > 10% of revenue",
                "Assets described as purpose-built or industry-specific",
                "High exit barriers mentioned"
            ],
            "Moderate": [
                "Fixed asset intensity 15-30% of revenue",
                "Capex intensity 5-10% of revenue",
                "Mix of specific and general assets"
            ],
            "Low": [
                "Fixed asset intensity < 15% of revenue",
                "Capex intensity < 5% of revenue",
                "Assets largely generic and redeployable",
                "Asset-light business model"
            ]
        },
        "learning_curve": {
            "Significant": [
                "Cost ratio declining over 10-year period",
                "Revenue growth > 100% over period",
                "Management explicitly references operational efficiency gains",
                "Margin improvement alongside volume growth"
            ],
            "Moderate": [
                "Some cost ratio improvement observed",
                "Revenue growth 50-100% over period",
                "Efficiency gains mentioned selectively"
            ],
            "Minimal": [
                "No meaningful cost ratio improvement",
                "Limited revenue growth",
                "No efficiency gain references in documents"
            ]
        },
        "regulatory_moat": {
            "Strong": [
                "Licenses explicitly mentioned as barriers",
                "Regulatory approvals required for entry",
                "Patents protecting core products",
                "Management credits regulation as competitive protection",
                "Evidence of incumbents shaping regulation"
            ],
            "Moderate": [
                "Some regulatory requirements exist",
                "Partial IP protection present",
                "Compliance burden present but surmountable"
            ],
            "Weak": [
                "No significant regulatory barriers",
                "No patents or IP mentioned",
                "Easy regulatory compliance for new entrants"
            ]
        },
        "incumbent_aggression": {
            "High": [
                "Management explicitly references competitive retaliation",
                "Historical evidence of price wars",
                "Capacity preemption strategy mentioned",
                "Aggressive marketing spend on entry threats",
                "Precommitment contracts with customers"
            ],
            "Moderate": [
                "Some competitive response mentioned",
                "Selective price matching behaviour",
                "Moderate customer lock-in strategies"
            ],
            "Low": [
                "No deterrence behaviour evident",
                "Passive competitive responses only",
                "No precommitment mechanisms mentioned"
            ]
        }
    }

    F06_RUBRICS = {
        "rivalry_intensity": {
            "High": [
                "Price wars evident in documents",
                "Aggressive capacity expansion by multiple competitors",
                "Margin compression across peer set",
                "Management explicitly mentions intense competition",
                "Frequent competitive interactions noted",
                "No evidence of pricing discipline"
            ],
            "Moderate": [
                "Selective price competition in segments",
                "Some capacity discipline observed",
                "Mixed margin trends across peers",
                "Competition acknowledged but manageable"
            ],
            "Low": [
                "Stable pricing environment evident",
                "Disciplined capacity additions",
                "Stable or expanding margins across peers",
                "Management references rational pricing",
                "No price war history in documents"
            ]
        },
        "tacit_coordination": {
            "High": [
                "Management references rational pricing or disciplined capacity",
                "No prolonged price wars in documents",
                "Margins stable across peer set",
                "High HHI (concentrated market)",
                "High firm similarity signals",
                "Low demand variability",
                "Industry association activity mentioned"
            ],
            "Moderate": [
                "Partial pricing discipline evident",
                "Some coordination signals but mixed",
                "Moderate HHI with some similarity"
            ],
            "Low": [
                "Price war history evident",
                "Aggressive capacity additions",
                "Wide margin divergence across peers",
                "Management mentions competitive pricing pressure",
                "Fragmented market structure"
            ]
        },
        "industry_leader": {
            "Yes — disciplined": [
                "Clear market share leader identified",
                "Leader maintains pricing discipline",
                "Leader signals capacity restraint",
                "Leader avoids aggressive share grabs",
                "Other firms follow leader pricing"
            ],
            "Yes — aggressive": [
                "Clear market share leader identified",
                "Leader pursues aggressive pricing",
                "Leader expands capacity aggressively",
                "Leader disrupts industry structure"
            ],
            "No clear leader": [
                "No single dominant player",
                "Market share fragmented",
                "No consistent pricing signal from any single firm"
            ]
        },
        "demand_variability": {
            "High": [
                "Revenue std dev > 15% across peers",
                "Cyclical demand patterns evident",
                "Management references demand volatility explicitly",
                "Wide revenue swings in downturn years"
            ],
            "Moderate": [
                "Revenue std dev 5-15% across peers",
                "Some cyclicality but manageable",
                "Moderate demand fluctuations noted"
            ],
            "Low": [
                "Revenue std dev < 5% across peers",
                "Stable demand growth pattern",
                "Management references predictable demand environment",
                "Recession-resistant revenue base"
            ]
        },
        "fixed_cost_level": {
            "High": [
                "Fixed asset intensity > 30% of revenue",
                "High depreciation relative to revenue",
                "Management references operating leverage explicitly",
                "Capacity utilisation mentioned as key metric"
            ],
            "Moderate": [
                "Fixed asset intensity 15-30% of revenue",
                "Mix of fixed and variable cost structure",
                "Some operating leverage present"
            ],
            "Low": [
                "Fixed asset intensity < 15% of revenue",
                "Predominantly variable cost structure",
                "Asset-light model evident",
                "Low depreciation relative to revenue"
            ]
        },
        "firm_similarity": {
            "High": [
                "Similar revenue scale across peers",
                "Similar margin profiles",
                "Similar capex intensity",
                "Comparable business models",
                "Aligned strategic priorities"
            ],
            "Moderate": [
                "Some size differences but comparable",
                "Margin divergence in some segments",
                "Partial model similarity"
            ],
            "Low": [
                "Wide revenue size disparity",
                "Significantly different margin profiles",
                "Different business models or segments",
                "Divergent strategic priorities"
            ]
        },
        "industry_growth": {
            "High": [
                "Universe revenue CAGR > 15%",
                "Management references strong demand tailwinds",
                "Multiple peers reporting strong growth",
                "TAM expansion commentary in documents"
            ],
            "Moderate": [
                "Universe revenue CAGR 7-15%",
                "Steady growth with some variability",
                "Management references stable demand"
            ],
            "Low": [
                "Universe revenue CAGR 0-7%",
                "Mature market commentary",
                "Limited growth catalysts mentioned"
            ],
            "Declining": [
                "Universe revenue CAGR < 0%",
                "Management references market contraction",
                "Peers reporting revenue declines"
            ]
        }
    }

    ADDITIONAL_DOCUMENTS_MAP = {
        "supplier_power": [
            "Supplier contracts or procurement reports",
            "Raw material cost breakdown schedules",
            "Industry supplier concentration reports",
            "Management discussion on input costs"
        ],
        "buyer_power": [
            "Customer concentration disclosures",
            "Top customer revenue breakdowns",
            "Customer retention or churn data",
            "Segment-wise revenue by customer type"
        ],
        "substitution_threat": [
            "Industry technology trend reports",
            "Competitor product launch announcements",
            "Management commentary on new entrants",
            "Sector disruption analysis reports"
        ],
        "switching_costs": [
            "Contract duration disclosures",
            "Customer integration case studies",
            "Proprietary system documentation",
            "Churn rate or retention metrics"
        ],
        "barriers_to_entry": [
            "Capital expenditure benchmarks",
            "Regulatory filing requirements",
            "Patent and IP registrations",
            "Minimum efficient scale studies"
        ],
        "rivalry_intensity": [
            "Competitor pricing announcements",
            "Market share movement reports",
            "Industry pricing trend analyses",
            "Management commentary on competition"
        ],
        "network_effects": [
            "Platform usage and user growth metrics",
            "Customer acquisition cost trends",
            "Management commentary on network dynamics",
            "Technology architecture descriptions"
        ],
        "regulatory_moat": [
            "Regulatory filing history",
            "Patent registration records",
            "Government policy documents",
            "Industry association reports"
        ],
        "incumbent_aggression": [
            "Competitor response history reports",
            "Pricing strategy disclosures",
            "Capacity addition announcements",
            "Customer contract terms disclosures"
        ],
        "tacit_coordination": [
            "Pricing strategy disclosures",
            "Capacity addition announcements",
            "Industry association meeting notes",
            "Competitor response history analysis"
        ],
        "industry_leader": [
            "Market share data over 10 years",
            "Industry pricing leadership analysis",
            "Competitor capacity announcements"
        ]
    }

    def validate_score_block(self, force_name: str, score_block: dict) -> tuple[bool, list[str]]:
        """
        Validates a single force score block.
        """
        errors = []
        
        # 1. score
        score = score_block.get("score")
        if not score or score not in self.VALID_SCORES:
            errors.append(f"Invalid or missing score: {score}")
            
        # 2. primary_evidence
        pe = score_block.get("primary_evidence")
        if isinstance(pe, dict):
            if not pe.get("document"): errors.append("primary_evidence missing document")
            if not pe.get("excerpt"): errors.append("primary_evidence missing excerpt")
            if not pe.get("year"): errors.append("primary_evidence missing year")
        else:
            errors.append("primary_evidence must be a dictionary")
            
        # 3. supporting_evidence
        se = score_block.get("supporting_evidence")
        if not isinstance(se, list):
            errors.append("supporting_evidence must be a list")
            
        # 4. confidence
        conf = score_block.get("confidence")
        if not conf or conf not in self.VALID_CONFIDENCE:
            errors.append(f"Invalid or missing confidence: {conf}")
            
        # 5. contradicting_evidence
        if "contradicting_evidence" not in score_block:
            errors.append("Missing contradicting_evidence key")
            
        # 6. quantitative_anchor
        if "quantitative_anchor" not in score_block:
            errors.append("Missing quantitative_anchor key")
            
        return len(errors) == 0, errors

    def validate_all_scores(self, scores: dict) -> tuple[bool, dict]:
        """
        Calls validate_score_block() for each force in scores dict.
        """
        all_valid = True
        validation_report = {}
        
        for force_name, score_block in scores.items():
            if not isinstance(score_block, dict):
                all_valid = False
                validation_report[force_name] = {
                    "valid": False,
                    "errors": ["Score block is not a dictionary"]
                }
                continue
                
            is_valid, errors = self.validate_score_block(force_name, score_block)
            if not is_valid:
                all_valid = False
            validation_report[force_name] = {
                "valid": is_valid,
                "errors": errors
            }
            
        return all_valid, validation_report

    def generate_confidence_flags(self, scores: dict, agent_id: str) -> list[dict]:
        """
        Generates flags for forces where confidence == "low".
        """
        flags = []
        for force_name, score_block in scores.items():
            if isinstance(score_block, dict) and score_block.get("confidence") == "low":
                docs = self.ADDITIONAL_DOCUMENTS_MAP.get(force_name, ["No specific documents recommended"])
                score = score_block.get("score", "Unknown")
                
                flags.append({
                    "agent_id": agent_id,
                    "force": force_name,
                    "score": score,
                    "confidence": "low",
                    "warning": f"Limited direct evidence for {force_name} scoring in {agent_id}. Score inferred from indirect signals.",
                    "recommended_documents": docs
                })
        return flags

    def format_confidence_warnings(self, confidence_flags: list[dict]) -> str:
        """
        Formats confidence flags as markdown warning block for inclusion in report section.
        """
        if not confidence_flags:
            return ""
            
        lines = [
            "---",
            "⚠ **Evidence Quality Notices**",
            ""
        ]
        
        for flag in confidence_flags:
            force = flag.get("force", "Unknown").replace("_", " ").title()
            score = flag.get("score", "Unknown")
            lines.append(f"**{force} (Score: {score}):** Limited direct evidence detected. Score inferred from indirect signals. Confidence: Low.")
            lines.append("")
            lines.append("*Recommended additional documents to improve confidence:*")
            for doc in flag.get("recommended_documents", []):
                lines.append(f"- {doc}")
            lines.append("")
            
        lines.append("---")
        return "\n".join(lines)

    def format_appendix_recommendations(self, confidence_flags: list[dict], company_name: str) -> str:
        """
        Formats a structured appendix entry for all low confidence findings across the run.
        """
        if not confidence_flags:
            return ""
            
        lines = [
            "## Recommended Additional Documents",
            f"**Company:** {company_name}",
            "",
            "The following additional documents would improve analytical confidence for the sections noted:",
            ""
        ]
        
        for flag in confidence_flags:
            force = flag.get("force", "Unknown").replace("_", " ").title()
            lines.append(f"### {force} Analysis")
            lines.append("Current confidence: Low")
            lines.append("Recommended documents:")
            for doc in flag.get("recommended_documents", []):
                lines.append(f"- {doc}")
            lines.append("")
            
        return "\n".join(lines)

    def apply_gross_margin_override(self, scores: dict, gross_margin_trend: str) -> tuple[dict, list[str]]:
        """
        Applies programmatic gross margin override rules after LLM scoring.
        """
        updated_scores = json.loads(json.dumps(scores)) # deep copy
        override_flags = []
        
        # RULE 1
        if gross_margin_trend == "contracting":
            supp_block = updated_scores.get("supplier_power")
            if supp_block and supp_block.get("score") == "Low":
                supp_block["score"] = "Moderate"
                override_flags.append("Supplier power score upgraded from Low to Moderate: contracting gross margin trend detected (F02). Review evidence carefully.")
                
        # RULE 2
        if gross_margin_trend == "expanding":
            buy_block = updated_scores.get("buyer_power")
            if buy_block and buy_block.get("score") == "High":
                override_flags.append("High buyer power score noted despite expanding gross margins (F02). Verify evidence quality — potential contradiction detected.")
                
        return updated_scores, override_flags

    def compute_summary_scores(self, scores: dict) -> dict:
        """
        Converts Low/Moderate/High to numeric for summary reporting only.
        """
        mapping = {
            "Low": 1,
            "Moderate": 2,
            "High": 3
        }
        
        result = {}
        for force_name, score_block in scores.items():
            if isinstance(score_block, dict):
                lbl = score_block.get("score")
                num = mapping.get(lbl, 0)
                result[force_name] = {
                    "label": lbl,
                    "numeric": num
                }
        return result
