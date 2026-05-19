import json
from pathlib import Path
from typing import Any
from loguru import logger

class ExecutiveSummaryGenerator:
    """
    Generates the executive summary by reading all F01-F06 findings 
    from the context broker and making a single focused LLM call.
    """
    
    SYSTEM_PROMPT = """You are a senior equity research analyst
at a top-tier institutional investment firm.
Write the Executive Summary for a qualitative
research report on an Indian listed company.

The summary will appear at the front of the
report and is read first by portfolio managers
and investment committee members.
It must be authoritative, precise, and
immediately convey the investment-relevant
qualitative picture.

Writing standards:
- Formal third-person analyst report style
- Every claim must reference provided data
- No external knowledge
- Present tense throughout"""

    USER_PROMPT_TEMPLATE = """# Executive Summary Generation
# Company: {company_name}
# Analysis Period: {start_year} to {end_year}

## Key Findings Across All Sections
{key_findings_table}

## Quantitative Snapshot
{quantitative_snapshot_table}

## Qualitative Scores Summary
{scores_summary_table}

─────────────────────────────────────
OUTPUT INSTRUCTIONS:
─────────────────────────────────────

Write the Executive Summary with EXACTLY
these subsections in order:

### Investment Thesis
2-3 sentences capturing the core qualitative
investment thesis. Reference ROIC spread,
competitive position, and primary structural
advantage or risk. This is the most important
paragraph in the report.

### Financial Quality
2-3 sentences on ROIC vs WACC, trend, and
future value component. Reference specific
values.

### Competitive Position
2-3 sentences on industry structure, market
share position, and entry barriers protecting
that position.

### Key Risks
3 specific bullet points — each one sentence.
Most important qualitative risks identified
across all 6 frameworks.
Format:
- {Risk 1}
- {Risk 2}
- {Risk 3}

### Key Strengths
3 specific bullet points — each one sentence.
Most important qualitative strengths identified
across all 6 frameworks.
Format:
- {Strength 1}
- {Strength 2}
- {Strength 3}

### Analytical Scope Note
One sentence noting this report covers
frameworks F01-F06 of a broader qualitative
research framework.

─────────────────────────────────────
CONSTRAINTS:
─────────────────────────────────────
- Total output 400-500 words maximum
- Every statistic cited must be in
  provided tables
- No hedging language
- No generic statements — every sentence
  must be company-specific
- Formal analyst report tone throughout
- Key Risks and Strengths must each have
  exactly 3 bullets"""

    def __init__(self, config: dict, llm_client: Any):
        """
        Stores config and llm_client.
        """
        self.config = config
        self.llm_client = llm_client

    def load_all_findings(self, broker: Any) -> dict:
        """
        Reads all 6 agent findings from broker.
        Also reads all key_findings.
        """
        findings = {}
        for agent_id in ["F01", "F02", "F03", "F04", "F05", "F06"]:
            data = broker.read(agent_id)
            if data:
                findings[agent_id] = data
                
        # To get key findings and specific findings dict we check the saved json
        # Since the broker has the raw json output, we can extract from there
        key_findings = {}
        processed_dir = Path(self.config.get("processed_dir", "./output/processed"))
        focal_company = self.config.get("focal_company", "Unknown")
        frameworks_dir = processed_dir / focal_company / "frameworks"
        
        for agent_id in ["F01", "F02", "F03", "F04", "F05", "F06"]:
            json_path = frameworks_dir / f"{agent_id}.json"
            if json_path.exists():
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        key_findings[agent_id] = data.get("key_finding", "Missing.")
                except Exception:
                    key_findings[agent_id] = "Missing."
            else:
                key_findings[agent_id] = "Not generated."
                
        return {
            "findings": findings,
            "key_findings": key_findings
        }

    def build_executive_summary_prompt(
        self,
        all_findings: dict,
        company_name: str,
        session: dict) -> str:
        """
        Builds focused prompt for executive summary.
        """
        kf = all_findings.get("key_findings", {})
        key_findings_table = f"""Section | Key Finding
F01 Introduction      | {kf.get("F01", "-")}
F02 Why Strategy      | {kf.get("F02", "-")}
F03 Lay of Land       | {kf.get("F03", "-")}
F04 Three Forces      | {kf.get("F04", "-")}
F05 New Entrants      | {kf.get("F05", "-")}
F06 Rivalry           | {kf.get("F06", "-")}"""

        f01 = all_findings.get("findings", {}).get("F01", {})
        f03 = all_findings.get("findings", {}).get("F03", {})
        f04 = all_findings.get("findings", {}).get("F04", {})
        f05 = all_findings.get("findings", {}).get("F05", {})
        f06 = all_findings.get("findings", {}).get("F06", {})
        
        quantitative_snapshot_table = f"""Metric                    | Value
Latest ROIC               | {f01.get("latest_roic", "-")}%
WACC                      | {f01.get("wacc", "-")}%
ROIC Spread               | {f01.get("roic_spread", "-")}%
ROIC Trend                | {f01.get("trend_direction", "-")}
Future Value %            | {f01.get("future_value_pct", "-")}%
Industry Attractiveness   | {f03.get("industry_attractiveness_score", "-")}
Focal Market Share        | {f03.get("focal_market_share", "-")}%
Market Share Trend        | {f03.get("market_share_trend", "-")}
Industry Structure        | {f03.get("industry_structure", "-")}
Overall Entry Threat      | {f05.get("overall_entry_threat", "-")}
Overall Force Pressure    | {f04.get("overall_force_pressure", "-")}
Overall Rivalry Intensity | {f06.get("overall_rivalry_intensity", "-")}
Barriers to Entry         | {f05.get("barriers_to_entry_score", "-")}
Tacit Coordination        | {f06.get("tacit_coordination_score", "-")}"""

        def get_score(f_dict, metric):
            return f_dict.get(metric, "-")
            
        def get_conf(f_dict, metric):
            # Try to get confidence flag length or default to High
            flags = f_dict.get("confidence_flags", [])
            return "High" if not flags else "Moderate"

        scores_summary_table = f"""Framework | Primary Score | Confidence
F04 Supplier Power    | {get_score(f04, 'supplier_power_score')} | {get_conf(f04, 'supplier_power_score')}
F04 Buyer Power       | {get_score(f04, 'buyer_power_score')} | {get_conf(f04, 'buyer_power_score')}
F04 Substitution      | {get_score(f04, 'substitution_threat_score')} | {get_conf(f04, 'substitution_threat_score')}
F04 Switching Costs   | {get_score(f04, 'switching_costs_score')} | {get_conf(f04, 'switching_costs_score')}
F05 Barriers to Entry | {get_score(f05, 'barriers_to_entry_score')} | {get_conf(f05, 'barriers_to_entry_score')}
F05 Network Effects   | {get_score(f05, 'network_effects_score')} | {get_conf(f05, 'network_effects_score')}
F05 Regulatory Moat   | {get_score(f05, 'regulatory_moat_score')} | {get_conf(f05, 'regulatory_moat_score')}
F06 Rivalry Intensity | {get_score(f06, 'rivalry_intensity_score')} | {get_conf(f06, 'rivalry_intensity_score')}
F06 Coordination      | {get_score(f06, 'tacit_coordination_score')} | {get_conf(f06, 'tacit_coordination_score')}
F06 Industry Growth   | {get_score(f06, 'industry_growth_score')} | {get_conf(f06, 'industry_growth_score')}"""

        start_year = session.get("start_year", "FY2015")
        end_year = session.get("end_year", "FY2025")

        prompt = self.USER_PROMPT_TEMPLATE.replace("{company_name}", company_name)
        prompt = prompt.replace("{start_year}", start_year)
        prompt = prompt.replace("{end_year}", end_year)
        prompt = prompt.replace("{key_findings_table}", key_findings_table)
        prompt = prompt.replace("{quantitative_snapshot_table}", quantitative_snapshot_table)
        prompt = prompt.replace("{scores_summary_table}", scores_summary_table)
        
        return prompt

    def generate(self,
                 broker: Any,
                 company_name: str,
                 session: dict) -> str:
        """
        Builds prompt and calls LLM once.
        Returns executive summary markdown string.
        """
        try:
            all_findings = self.load_all_findings(broker)
            prompt = self.build_executive_summary_prompt(all_findings, company_name, session)
            response = self.llm_client.complete(self.SYSTEM_PROMPT, prompt)
            return response
        except Exception as e:
            logger.error(f"Executive summary generation failed: {e}", exc_info=True)
            return "*Executive summary generation failed. Please review individual section outputs.*"
