import json
import traceback
from pathlib import Path
from typing import Any
from loguru import logger
from datetime import datetime
import markdown
from jinja2 import Template
try:
    from weasyprint import HTML, CSS
    WEASYPRINT_AVAILABLE = True
except Exception as e:
    logger.warning(f"WeasyPrint is not fully available on this system due to missing GTK+ dependencies ({e}). Falling back to HTML report compilation.")
    WEASYPRINT_AVAILABLE = False

from tools.chart_generator import ChartGenerator
from tools.executive_summary_generator import ExecutiveSummaryGenerator

HTML_REPORT_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
/* CSS DESIGN SPECIFICATION */
:root {
  --accent: #1B3A6B;
  --accent-mid: #4A7AB5;
  --accent-light: #D6E4F0;
  --text: #2C2C2C;
  --text-light: #666666;
  --border: #E0E0E0;
  --white: #FFFFFF;
  --row-alt: #F7F9FC;
  --danger: #C0392B;
  --warning: #F39C12;
}

body {
    font-family: 'DejaVu Sans', sans-serif;
    font-size: 10pt;
    line-height: 1.6;
    color: var(--text);
}

@page {
  size: A4;
  margin: 2.5cm 2cm 2.5cm 2cm;
  @top-left {
    content: "{{ company_name }} ({{ ticker }})";
    font-size: 8pt;
    color: #666666;
  }
  @top-right {
    content: "{{ report_date }}";
    font-size: 8pt;
    color: #666666;
  }
  @bottom-left {
    content: "Hedge Fund Research Agent";
    font-size: 8pt;
    color: #666666;
  }
  @bottom-center {
    content: counter(page);
    font-size: 8pt;
    color: #666666;
  }
  @bottom-right {
    content: "Confidential — For Internal Use";
    font-size: 8pt;
    color: #666666;
  }
}

@page :first {
  margin: 0;
  @top-left { content: none; }
  @top-right { content: none; }
  @bottom-left { content: none; }
  @bottom-center { content: none; }
  @bottom-right { content: none; }
}

h1 {
    font-size: 28pt;
    color: #1B3A6B;
    font-weight: bold;
}
h2 {
    font-size: 16pt;
    color: #1B3A6B;
    font-weight: bold;
}
h3 {
    font-size: 12pt;
    color: #1B3A6B;
    font-weight: 600;
}
p {
    margin-bottom: 12px;
}

.cover-page {
    height: 100vh;
    background-color: #1B3A6B;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
}
.cover-top {
    padding: 4cm 2.5cm;
}
.cover-bar {
    background-color: white;
    height: 10px;
}
.cover-top h1 {
    font-size: 32pt;
    color: white;
    font-weight: bold;
    letter-spacing: 2px;
    margin-top: 40px;
    margin-bottom: 0;
}
.report-title {
    font-size: 16pt;
    color: #D6E4F0;
    margin-top: 8px;
}
.cover-divider {
    border: none;
    border-top: 1px solid white;
    width: 60px;
    margin: 20px 0;
}
.cover-meta {
    font-size: 12pt;
    color: white;
    opacity: 0.85;
}
.cover-period {
    font-size: 10pt;
    color: #D6E4F0;
}
.cover-bottom {
    padding: 0 2.5cm 2cm;
}
.cover-date {
    font-size: 10pt;
    color: white;
}
.cover-agent {
    font-size: 9pt;
    color: #D6E4F0;
}
.cover-disclaimer {
    font-size: 8pt;
    color: white;
    opacity: 0.7;
}

.page-break {
    page-break-before: always;
}

.toc li {
    font-size: 11pt;
}
.toc li > ul > li {
    font-size: 10pt;
    color: #666666;
}

.section-title-bar {
    background-color: #1B3A6B;
    color: white;
    padding: 12px 20px;
    font-size: 14pt;
    font-weight: bold;
    margin-bottom: 20px;
}
.section-title-bar.appendix {
    background-color: #4A7AB5;
}

.key-finding-box {
    border-left: 4px solid #1B3A6B;
    background-color: #D6E4F0;
    padding: 10px 16px;
    margin-bottom: 20px;
}
.kf-label {
    color: #1B3A6B;
    font-weight: bold;
    font-size: 8pt;
    display: block;
    margin-bottom: 4px;
}
.kf-text {
    font-size: 10pt;
    font-weight: bold;
}

table {
    width: 100%;
    border-collapse: collapse;
    font-size: 9pt;
    margin-bottom: 20px;
}
th {
    background-color: #1B3A6B;
    color: white;
    font-weight: bold;
    padding: 8px 10px;
    text-align: left;
}
tr:nth-child(even) {
    background-color: white;
}
tr:nth-child(odd) {
    background-color: #F7F9FC;
}
td {
    padding: 6px 10px;
    border-bottom: 1px solid #E0E0E0;
}
caption {
    font-size: 8pt;
    font-style: italic;
    color: #666666;
    margin-top: 4px;
    text-align: left;
    caption-side: bottom;
}

.chart-container {
    max-width: 100%;
    margin: 20px auto;
    text-align: center;
}
.chart-container img {
    max-width: 100%;
    height: auto;
}
.chart-caption {
    font-size: 8pt;
    font-style: italic;
    color: #666666;
}

.confidence-warning {
    border: 1px solid #F39C12;
    background-color: #FEF9E7;
    border-radius: 4px;
    padding: 10px 14px;
    font-size: 9pt;
    margin-bottom: 15px;
}
  </style>
</head>
<body>

  <!-- COVER PAGE -->
  <div class="cover-page">
    <div class="cover-top">
      <div class="cover-bar"></div>
      <h1>{{ company_name }}</h1>
      <p class="report-title">
        Qualitative Research Report
      </p>
      <hr class="cover-divider">
      <p class="cover-meta">
        {{ ticker }} | NSE/BSE | {{ sector }}
      </p>
      <p class="cover-period">
        Analysis Period: {{ start_year }}
        – {{ end_year }}
      </p>
    </div>
    <div class="cover-bottom">
      <p class="cover-date">{{ report_date }}</p>
      <p class="cover-agent">
        Prepared by Hedge Fund Research
        Agent v1.0
      </p>
      <p class="cover-disclaimer">
        This report is generated by an AI
        research agent for internal analytical
        purposes only. Not investment advice.
      </p>
    </div>
  </div>

  <!-- TABLE OF CONTENTS -->
  <div class="page-break">
    <h2>Contents</h2>
    <ol class="toc">
      <li>Executive Summary</li>
      <li>Introduction & ROIC Foundation</li>
      <li>Why Strategy Matters</li>
      <li>Lay of the Land</li>
      <li>Bargaining Power of Suppliers,
          Buyers & Substitution</li>
      <li>Threat of New Entrants &
          Barriers to Entry</li>
      <li>Rivalry Among Existing Firms</li>
      <li>Appendices</li>
    </ol>
  </div>

  <!-- EXECUTIVE SUMMARY -->
  <div class="page-break">
    <div class="section-title-bar">
      Executive Summary
    </div>
    <div class="section-body">
      {{ executive_summary | safe }}
    </div>
  </div>

  <!-- SECTION 1: F01 -->
  <div class="page-break">
    <div class="section-title-bar">
      1. Introduction & ROIC Foundation
    </div>
    <div class="key-finding-box">
      <span class="kf-label">KEY FINDING</span>
      <span class="kf-text">
        {{ f01_key_finding }}
      </span>
    </div>
    {% if charts.roic_wacc %}
    <div class="chart-container">
      <img src="{{ charts.roic_wacc }}"
           alt="ROIC vs WACC Trend">
      <p class="chart-caption">
        Figure 1: ROIC vs WACC Trend
        ({{ start_year }}–{{ end_year }})
      </p>
    </div>
    {% endif %}
    <div class="section-body">
      {{ f01_output | safe }}
    </div>
  </div>

  <!-- SECTION 2: F02 -->
  <div class="page-break">
    <div class="section-title-bar">
      2. Why Strategy Matters
    </div>
    <div class="key-finding-box">
      <span class="kf-label">KEY FINDING</span>
      <span class="kf-text">
        {{ f02_key_finding }}
      </span>
    </div>
    {% if charts.peer_roic %}
    <div class="chart-container">
      <img src="{{ charts.peer_roic }}"
           alt="Peer ROIC Comparison">
      <p class="chart-caption">
        Figure 2: Peer ROIC Comparison
        ({{ start_year }}–{{ end_year }})
      </p>
    </div>
    {% endif %}
    <div class="section-body">
      {{ f02_output | safe }}
    </div>
  </div>

  <!-- SECTION 3: F03 -->
  <div class="page-break">
    <div class="section-title-bar">
      3. Lay of the Land
    </div>
    <div class="key-finding-box">
      <span class="kf-label">KEY FINDING</span>
      <span class="kf-text">
        {{ f03_key_finding }}
      </span>
    </div>
    {% if charts.market_share %}
    <div class="chart-container">
      <img src="{{ charts.market_share }}"
           alt="Proxy Market Share">
      <p class="chart-caption">
        Figure 3: Proxy Market Share —
        Listed Universe
        ({{ start_year }}–{{ end_year }})
      </p>
    </div>
    {% endif %}
    <div class="section-body">
      {{ f03_output | safe }}
    </div>
  </div>

  <!-- SECTION 4: F04 -->
  <div class="page-break">
    <div class="section-title-bar">
      4. Bargaining Power of Suppliers,
      Buyers & Substitution
    </div>
    <div class="key-finding-box">
      <span class="kf-label">KEY FINDING</span>
      <span class="kf-text">
        {{ f04_key_finding }}
      </span>
    </div>
    <div class="section-body">
      {{ f04_output | safe }}
    </div>
  </div>

  <!-- SECTION 5: F05 -->
  <div class="page-break">
    <div class="section-title-bar">
      5. Threat of New Entrants &
      Barriers to Entry
    </div>
    <div class="key-finding-box">
      <span class="kf-label">KEY FINDING</span>
      <span class="kf-text">
        {{ f05_key_finding }}
      </span>
    </div>
    <div class="section-body">
      {{ f05_output | safe }}
    </div>
  </div>

  <!-- SECTION 6: F06 -->
  <div class="page-break">
    <div class="section-title-bar">
      6. Rivalry Among Existing Firms
    </div>
    <div class="key-finding-box">
      <span class="kf-label">KEY FINDING</span>
      <span class="kf-text">
        {{ f06_key_finding }}
      </span>
    </div>
    <div class="section-body">
      {{ f06_output | safe }}
    </div>
  </div>

  <!-- APPENDIX A -->
  <div class="page-break">
    <div class="section-title-bar appendix">
      Appendix A: Data Sources & Methodology
    </div>
    <div class="section-body">
      {{ appendix_sources | safe }}
    </div>
  </div>

  <!-- APPENDIX B -->
  <div class="page-break">
    <div class="section-title-bar appendix">
      Appendix B: Evidence Quality & Confidence
    </div>
    <div class="section-body">
      {{ appendix_confidence | safe }}
    </div>
  </div>

  <!-- APPENDIX C -->
  <div class="page-break">
    <div class="section-title-bar appendix">
      Appendix C: Recommended Additional
      Documents
    </div>
    <div class="section-body">
      {{ appendix_recommendations | safe }}
    </div>
  </div>

  <!-- APPENDIX D -->
  <div class="page-break">
    <div class="section-title-bar appendix">
      Appendix D: Data Quality Flags
    </div>
    <div class="section-body">
      {{ appendix_data_flags | safe }}
    </div>
  </div>

</body>
</html>"""

class ReportAssembler:
    """
    Assembles all framework outputs, executive summary, charts, and appendices
    into a single professional PDF report.
    Uses Jinja2 for templating and WeasyPrint for PDF generation.
    """
    def __init__(self, config: dict, focal_company: str, session: dict):
        self.config = config
        self.focal_company = focal_company
        self.session = session
        
        self.processed_dir = Path(config.get("paths", {}).get("processed_dir", "processed"))
        self.date_str = datetime.now().strftime("%Y%m%d")
        
        base_out = Path(config.get("output_dir", "./output"))
        self.output_dir = base_out / self.focal_company / "reports" / self.date_str
        self.charts_dir = self.output_dir / "charts"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.chart_generator = ChartGenerator(self.output_dir)

    def load_framework_outputs(self) -> dict:
        """
        Loads all 6 framework JSON outputs.
        """
        frameworks_dir = self.processed_dir / self.focal_company / "frameworks"
        outputs = {}
        for agent_id in ["F01", "F02", "F03", "F04", "F05", "F06"]:
            path = frameworks_dir / f"{agent_id}.json"
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        outputs[agent_id] = json.load(f)
                except Exception as e:
                    logger.warning(f"Error loading {path}: {e}")
            
            if agent_id not in outputs:
                outputs[agent_id] = {
                    "agent_id": agent_id,
                    "status": "missing",
                    "key_finding": "Section not generated.",
                    "output": "[Section pending]",
                    "findings": {}
                }
        return outputs

    def load_appendix_content(self) -> dict:
        """
        Loads all appendix content.
        """
        frameworks_dir = self.processed_dir / self.focal_company / "frameworks"
        
        # Confidence flags
        conf_flags = []
        for agent_id in ["F04", "F05", "F06"]:
            path = frameworks_dir / f"{agent_id}_confidence_flags.json"
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        conf_flags.extend(json.load(f))
                except Exception as e:
                    logger.warning(f"Skipping missing or invalid {path}: {e}")
                    
        conf_md = ""
        for flag in conf_flags:
            conf_md += f"- **{flag.get('factor', 'Unknown')}**: {flag.get('reason', 'N/A')}\n"
        if not conf_md:
            conf_md = "No evidence quality warnings generated."
            
        # Appendix recommendations
        recs = ""
        for agent_id in ["F04", "F05", "F06"]:
            path = frameworks_dir / f"{agent_id}_appendix_recommendations.md"
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        recs += f.read() + "\n\n"
                except Exception as e:
                    logger.warning(f"Skipping missing {path}: {e}")
        if not recs.strip():
            recs = "No additional documents recommended."
            
        # Data quality flags
        flags_md = ""
        # The instructions say "Collect all data_quality_flags from all framework JSON outputs"
        # Since we load them in assemble, we can just read them from the json files or we can pass framework_outputs in.
        # But we don't have framework_outputs here. Let's just read the jsons again or parse the directory
        dq_flags = set()
        for agent_id in ["F01", "F02", "F03", "F04", "F05", "F06"]:
            path = frameworks_dir / f"{agent_id}.json"
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        flags = data.get("findings", {}).get("data_quality_flags", [])
                        for f_flag in flags:
                            dq_flags.add(f_flag)
                except Exception:
                    pass
                    
        for flag in dq_flags:
            flags_md += f"- {flag}\n"
        if not flags_md:
            flags_md = "No data quality flags."
            
        # Data sources
        sources_md = f"- **Focal Company Documents**: {', '.join(self.session.get('focal_company_documents', []))}\n"
        sources_md += f"- **Peer Company Documents**: {', '.join(self.session.get('peer_company_documents', []))}\n"
        sources_md += f"- **Analysis Period**: {self.session.get('start_year', 'FY2015')} to {self.session.get('end_year', 'FY2025')}\n"
        sources_md += f"- **Model**: {self.session.get('model', 'Unknown')}\n"
        sources_md += f"- **Run Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"

        return {
            "confidence_flags": conf_md,
            "recommendations": recs,
            "data_quality_flags": flags_md,
            "data_sources": sources_md
        }

    def generate_charts(self, framework_outputs: dict) -> dict:
        """
        Generates all 3 charts using ChartGenerator.
        """
        paths = {"roic_wacc": None, "peer_roic": None, "market_share": None}
        
        try:
            f01_findings = framework_outputs.get("F01", {}).get("findings", {})
            roic_series = f01_findings.get("roic_vs_wacc_by_year", {})
            if not roic_series and "trend_analysis" in f01_findings:
                roic_series = f01_findings["trend_analysis"].get("roic_vs_wacc_by_year", {})
                
            if roic_series:
                wacc = f01_findings.get("wacc", 10.0)
                p = self.chart_generator.generate_roic_wacc_chart(roic_series, self.focal_company, wacc)
                paths["roic_wacc"] = f"file:///{str(p.resolve()).replace(chr(92), '/')}" if p else None
        except Exception as e:
            logger.warning(f"Chart roic_wacc generation failed: {e}")

        try:
            f02_findings = framework_outputs.get("F02", {}).get("findings", {})
            peer_series = f02_findings.get("peer_roic_series", {})
            wacc = f02_findings.get("wacc", 10.0)
            if peer_series:
                p = self.chart_generator.generate_peer_roic_chart(peer_series, self.session.get("ticker", "TICKER"), wacc)
                paths["peer_roic"] = f"file:///{str(p.resolve()).replace(chr(92), '/')}" if p else None
        except Exception as e:
            logger.warning(f"Chart peer_roic generation failed: {e}")

        try:
            f03_findings = framework_outputs.get("F03", {}).get("findings", {})
            market_share = f03_findings.get("proxy_market_share", {})
            if market_share:
                p = self.chart_generator.generate_market_share_chart(market_share, self.session.get("ticker", "TICKER"))
                paths["market_share"] = f"file:///{str(p.resolve()).replace(chr(92), '/')}" if p else None
        except Exception as e:
            logger.warning(f"Chart market_share generation failed: {e}")

        return paths

    def build_html(self, framework_outputs: dict, executive_summary: str, charts: dict, appendix: dict) -> str:
        """
        Builds complete HTML document using Jinja2 template.
        """
        template = Template(self.load_html_template())
        
        def md2html(text):
            if not text:
                return ""
            return markdown.markdown(text, extensions=["tables", "fenced_code"])
            
        def kf(agent_id):
            f = framework_outputs.get(agent_id, {}).get("key_finding", "")
            return f if f else "Analysis complete. See section body for detailed findings."

        kwargs = {
            "company_name": self.focal_company,
            "ticker": self.session.get("ticker", "TICKER"),
            "sector": self.session.get("sector", "Sector"),
            "report_date": datetime.now().strftime("%B %d, %Y"),
            "start_year": self.session.get("start_year", "FY2015"),
            "end_year": self.session.get("end_year", "FY2025"),
            
            "executive_summary": md2html(executive_summary),
            
            "f01_key_finding": kf("F01"),
            "f01_output": md2html(framework_outputs.get("F01", {}).get("output", "")),
            
            "f02_key_finding": kf("F02"),
            "f02_output": md2html(framework_outputs.get("F02", {}).get("output", "")),
            
            "f03_key_finding": kf("F03"),
            "f03_output": md2html(framework_outputs.get("F03", {}).get("output", "")),
            
            "f04_key_finding": kf("F04"),
            "f04_output": md2html(framework_outputs.get("F04", {}).get("output", "")),
            
            "f05_key_finding": kf("F05"),
            "f05_output": md2html(framework_outputs.get("F05", {}).get("output", "")),
            
            "f06_key_finding": kf("F06"),
            "f06_output": md2html(framework_outputs.get("F06", {}).get("output", "")),
            
            "appendix_sources": md2html(appendix.get("data_sources", "")),
            "appendix_confidence": md2html(appendix.get("confidence_flags", "")),
            "appendix_recommendations": md2html(appendix.get("recommendations", "")),
            "appendix_data_flags": md2html(appendix.get("data_quality_flags", "")),
            
            "charts": charts
        }
        
        return template.render(**kwargs)

    def load_html_template(self) -> str:
        """
        Returns the complete HTML/CSS template string.
        """
        return HTML_REPORT_TEMPLATE

    def convert_to_pdf(self, html_content: str) -> Path:
        """
        Converts HTML to PDF using WeasyPrint. Falls back to saving HTML report.
        """
        ticker = self.session.get("ticker", "TICKER")
        html_path = self.output_dir / f"{ticker}_qualitative_research_{self.date_str}.html"
        
        # Always write the HTML report first for reference
        try:
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            logger.info(f"HTML reference report generated: {html_path}")
        except Exception as e:
            logger.error(f"Failed to write HTML reference report: {e}")
            
        if not WEASYPRINT_AVAILABLE:
            logger.warning("Skipping PDF generation because WeasyPrint is not fully available. Returning HTML path.")
            return html_path
            
        pdf_path = self.output_dir / f"{ticker}_qualitative_research_{self.date_str}.pdf"
        try:
            HTML(string=html_content).write_pdf(str(pdf_path))
            logger.info(f"PDF report generated: {pdf_path}")
            return pdf_path
        except Exception as e:
            logger.critical(f"PDF generation failed: {e}\n{traceback.format_exc()}")
            logger.warning("Falling back to HTML report path.")
            return html_path

    def assemble(self, broker: Any, llm_client: Any, session: dict) -> Path:
        """
        Master assembly method.
        """
        logger.info("Starting report assembly...")
        
        framework_outputs = self.load_framework_outputs()
        
        exec_gen = ExecutiveSummaryGenerator(self.config, llm_client)
        executive_summary = exec_gen.generate(broker, self.focal_company, session)
        
        charts = self.generate_charts(framework_outputs)
        
        appendix = self.load_appendix_content()
        
        html_content = self.build_html(framework_outputs, executive_summary, charts, appendix)
        
        out_path = self.convert_to_pdf(html_content)
        
        logger.info(f"Report assembly complete: {out_path}")
        return out_path
