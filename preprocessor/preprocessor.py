import os
import re
import json
import time
import datetime
from pathlib import Path
from typing import Dict, Any

from loguru import logger
from dotenv import load_dotenv
from rich.progress import Progress

from tools.pdf_extractor import (
    PageMapper, 
    AnnualReportExtractor, 
    ExchangeFilingExtractor, 
    TranscriptExtractor, 
    PresentationExtractor
)
from tools.chunker import SemanticChunker
from tools.context_builder import ContextBuilder

class PreProcessor:
    """
    Orchestrates the entire pre-processing pipeline. 
    Runs once before all subagents.
    Processes focal company and all peer companies.
    """
    def __init__(self, config: dict):
        """
        Initialise extractors, chunker, context builder, and log.
        """
        self.config = config
        load_dotenv()
        
        api_key = os.getenv("LLAMA_CLOUD_API_KEY", "")
        mode_std = os.getenv("LLAMA_PARSE_MODE_STANDARD", "accurate")
        mode_prem = os.getenv("LLAMA_PARSE_MODE_PREMIUM", "premium")
        
        self.page_mapper = PageMapper()
        self.ar_extractor = AnnualReportExtractor(api_key=api_key, parse_mode=mode_prem)
        self.ef_extractor = ExchangeFilingExtractor(api_key=api_key, parse_mode=mode_std)
        self.tr_extractor = TranscriptExtractor()
        self.pr_extractor = PresentationExtractor(api_key=api_key)
        self.chunker = SemanticChunker()
        self.context_builder = ContextBuilder(config)
        
        self.preprocessor_log: Dict[str, Any] = {}
        
        base_dir = Path(__file__).resolve().parent.parent
        input_dir = self.config.get("paths", {}).get("input_dir", "input")
        processed_dir = self.config.get("paths", {}).get("processed_dir", "processed")
        
        self.input_path = base_dir / input_dir
        self.processed_path = base_dir / processed_dir
        
        self.focal_company = self.config.get("run", {}).get("focal_company", "")
        self.peer_comps = self.config.get("run", {}).get("peer_comps", [])

    def _extract_with_retry(self, extractor: Any, *args, **kwargs) -> dict:
        """
        Wraps extraction calls with a retry mechanism (max 3 retries, 5s delay).
        """
        max_retries = 3
        for attempt in range(max_retries):
            try:
                return extractor.extract(*args, **kwargs)
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Extraction failed (attempt {attempt+1}/{max_retries}): {e}. Retrying in 5s...")
                    time.sleep(5)
                else:
                    logger.error(f"Extraction failed after {max_retries} attempts.")
                    raise e
        return {}

    def process_company(self, ticker: str, is_focal: bool, progress: Progress, task_id: int) -> None:
        """
        Processes all documents for a single company ticker.
        Runs extraction, chunking, and financial merging.
        """
        if ticker not in self.preprocessor_log:
            self.preprocessor_log[ticker] = {}
            
        input_dir = self.input_path / ticker
        if not input_dir.exists():
            return
            
        # Annual Reports
        ar_dir = input_dir / "annual_reports"
        if ar_dir.exists():
            for pdf_path in ar_dir.glob("*.pdf"):
                progress.update(task_id, description=f"[cyan]Processing {ticker} AR: {pdf_path.name}")
                self._process_annual_report(ticker, pdf_path)
                progress.advance(task_id)
                
        # Exchange Filings
        ef_dir = input_dir / "exchange_filings"
        if ef_dir.exists():
            for pdf_path in ef_dir.glob("*.pdf"):
                progress.update(task_id, description=f"[cyan]Processing {ticker} EF: {pdf_path.name}")
                self._process_exchange_filing(ticker, pdf_path)
                progress.advance(task_id)

        # Transcripts
        tr_dir = input_dir / "transcripts"
        if tr_dir.exists():
            for pdf_path in tr_dir.glob("*.pdf"):
                progress.update(task_id, description=f"[cyan]Processing {ticker} TR: {pdf_path.name}")
                self._process_transcript(ticker, pdf_path)
                progress.advance(task_id)

        # Presentations
        pr_dir = input_dir / "presentations"
        if pr_dir.exists():
            for pdf_path in pr_dir.glob("*.pdf"):
                progress.update(task_id, description=f"[cyan]Processing {ticker} PR: {pdf_path.name}")
                self._process_presentation(ticker, pdf_path)
                progress.advance(task_id)

    def _process_annual_report(self, ticker: str, pdf_path: Path) -> None:
        """Process a single Annual Report PDF."""
        doc_log = {
            "doc_type": "annual_report",
            "status": "success",
            "sections_extracted": [],
            "fallback_used": False,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        
        out_dir = self.processed_path / ticker / "raw_extracted" / "annual_reports" / pdf_path.name
        out_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            page_map = self.page_mapper.build_page_map(pdf_path)
            self.page_mapper.save_page_map(page_map, out_dir / "page_map.json")
            
            res = self._extract_with_retry(self.ar_extractor, pdf_path, page_map, out_dir)
            doc_log["sections_extracted"] = res.get("extracted_sections", [])
            doc_log["fallback_used"] = res.get("fallback_used", False)
            doc_log["status"] = res.get("status", "success")
            
            chunks_all = []
            if doc_log["fallback_used"]:
                fallback_file = out_dir / "full_fallback.txt"
                if fallback_file.exists():
                    with open(fallback_file, "r", encoding="utf-8") as f:
                        text = f.read()
                    chunks_all.extend(self.chunker.chunk(text, pdf_path.name, "annual_report"))
            else:
                for section in doc_log["sections_extracted"]:
                    sec_file = out_dir / f"{section}.txt"
                    if sec_file.exists():
                        with open(sec_file, "r", encoding="utf-8") as f:
                            text = f.read()
                        chunks_all.extend(self.chunker.chunk(text, pdf_path.name, "annual_report"))
                        
            if chunks_all:
                tagged_dir = self.processed_path / ticker / "tagged_chunks" / pdf_path.name
                tagged_dir.mkdir(parents=True, exist_ok=True)
                self.chunker.save_chunks(chunks_all, tagged_dir / "chunks.json")
                
        except Exception as e:
            logger.error(f"Failed processing AR {pdf_path.name}: {e}")
            doc_log["status"] = "failed"
            
        self.preprocessor_log[ticker][pdf_path.name] = doc_log

    def _process_exchange_filing(self, ticker: str, pdf_path: Path) -> None:
        """Process a single Exchange Filing PDF."""
        doc_log = {
            "doc_type": "exchange_filing",
            "status": "success",
            "sections_extracted": [],
            "fallback_used": False,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        
        out_dir = self.processed_path / ticker / "raw_extracted" / "exchange_filings" / pdf_path.name
        out_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            res = self._extract_with_retry(self.ef_extractor, pdf_path, out_dir)
            doc_log["status"] = res.get("status", "success")
            if res.get("yearly_extracted"):
                doc_log["sections_extracted"].append("yearly")
            if res.get("quarterly_extracted"):
                doc_log["sections_extracted"].append("quarterly")
        except Exception as e:
            logger.error(f"Failed processing EF {pdf_path.name}: {e}")
            doc_log["status"] = "failed"
            
        self.preprocessor_log[ticker][pdf_path.name] = doc_log

    def _process_transcript(self, ticker: str, pdf_path: Path) -> None:
        """Process a single Transcript PDF."""
        doc_log = {
            "doc_type": "transcript",
            "status": "success",
            "sections_extracted": [],
            "fallback_used": False,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        
        out_dir = self.processed_path / ticker / "raw_extracted" / "transcripts" / pdf_path.name
        out_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            res = self.tr_extractor.extract(pdf_path, out_dir)
            doc_log["status"] = res.get("status", "success")
            
            full_text_path = out_dir / "full_text.txt"
            if full_text_path.exists():
                with open(full_text_path, "r", encoding="utf-8") as f:
                    text = f.read()
                chunks = self.chunker.chunk(text, pdf_path.name, "transcript")
                if chunks:
                    tagged_dir = self.processed_path / ticker / "tagged_chunks" / pdf_path.name
                    tagged_dir.mkdir(parents=True, exist_ok=True)
                    self.chunker.save_chunks(chunks, tagged_dir / "chunks.json")
        except Exception as e:
            logger.error(f"Failed processing TR {pdf_path.name}: {e}")
            doc_log["status"] = "failed"
            
        self.preprocessor_log[ticker][pdf_path.name] = doc_log

    def _process_presentation(self, ticker: str, pdf_path: Path) -> None:
        """Process a single Presentation PDF."""
        doc_log = {
            "doc_type": "presentation",
            "status": "success",
            "sections_extracted": [],
            "fallback_used": False,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        
        out_dir = self.processed_path / ticker / "raw_extracted" / "presentations" / pdf_path.name
        out_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            res = self._extract_with_retry(self.pr_extractor, pdf_path, out_dir)
            doc_log["status"] = res.get("status", "success")
            
            full_text_path = out_dir / "full_text.txt"
            if full_text_path.exists():
                with open(full_text_path, "r", encoding="utf-8") as f:
                    text = f.read()
                chunks = self.chunker.chunk(text, pdf_path.name, "presentation")
                if chunks:
                    tagged_dir = self.processed_path / ticker / "tagged_chunks" / pdf_path.name
                    tagged_dir.mkdir(parents=True, exist_ok=True)
                    self.chunker.save_chunks(chunks, tagged_dir / "chunks.json")
        except Exception as e:
            logger.error(f"Failed processing PR {pdf_path.name}: {e}")
            doc_log["status"] = "failed"
            
        self.preprocessor_log[ticker][pdf_path.name] = doc_log

    def merge_financials(self, ticker: str) -> None:
        """
        Merges all exchange filing financial JSONs for a ticker into master files.
        If a ticker is a peer, saves to /processed/{focal}/financials/peers/{ticker}/.
        """
        is_focal = (ticker == self.focal_company)
        
        if is_focal:
            out_dir = self.processed_path / ticker / "financials"
        else:
            out_dir = self.processed_path / self.focal_company / "financials" / "peers" / ticker
            
        out_dir.mkdir(parents=True, exist_ok=True)
        
        raw_dir = self.processed_path / ticker / "raw_extracted" / "exchange_filings"
        
        def merge_type(period: str):
            master_dict = {}
            if raw_dir.exists():
                for json_file in raw_dir.rglob(f"financials_{period}.json"):
                    folder_name = json_file.parent.name
                    try:
                        with open(json_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        master_dict[folder_name] = data
                    except Exception as e:
                        logger.error(f"Failed to read {json_file}: {e}")
                        
            def sort_key(k):
                m = re.search(r'\d{4}(?:_Q[1-4])?', k)
                return m.group(0) if m else k
                
            sorted_keys = sorted(master_dict.keys(), key=sort_key)
            sorted_master = {k: master_dict[k] for k in sorted_keys}
            
            if not sorted_master:
                return
                
            json_out = out_dir / f"{period}_master.json"
            with open(json_out, "w", encoding="utf-8") as f:
                json.dump(sorted_master, f, indent=2)
                
            md_out = out_dir / f"{period}_master.md"
            with open(md_out, "w", encoding="utf-8") as f:
                for k in sorted_keys:
                    f.write(f"# {k}\n\n")
                    for tbl in sorted_master[k].get("tables", []):
                        f.write(f"### {tbl.get('table_name', '')}\n")
                        headers = tbl.get("headers", [])
                        if headers:
                            f.write("| " + " | ".join(headers) + " |\n")
                            f.write("|" + "|".join(["---"] * len(headers)) + "|\n")
                        for row in tbl.get("rows", []):
                            f.write("| " + row.get("label", "") + " | " + " | ".join(row.get("values", [])) + " |\n")
                        f.write("\n")
                        
        merge_type("yearly")
        merge_type("quarterly")

    def build_all_context_packages(self, broker_findings: dict) -> None:
        """
        Calls ContextBuilder.build() for each of the 13 agents.
        """
        agents = ["F01", "F02", "F03", "F04", "F05", "F06", "F07", 
                  "F08a", "F08b", "F08c", "F09", "F10", "F11"]
        for agent in agents:
            try:
                package = self.context_builder.build(agent, broker_findings)
                
                total = package.get("token_estimates", {}).get("total", 0)
                budget = 158000
                
                overflow_events = package.get("rebalancing_log", [])
                
                self.preprocessor_log[f"{agent}_context"] = {
                    "total_tokens": total,
                    "budget": budget,
                    "within_budget": total <= budget,
                    "rebalancing_applied": package.get("rebalancing_applied", False),
                    "overflow_events": overflow_events
                }
            except Exception as e:
                logger.error(f"Failed to build context package for {agent}: {e}")

    def save_log(self) -> None:
        """
        Saves preprocessor_log dict to /processed/{focal}/preprocessor_log.json
        """
        if not self.focal_company:
            return
            
        out_path = self.processed_path / self.focal_company / "preprocessor_log.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(self.preprocessor_log, f, indent=2)

    def run(self) -> None:
        """
        Master run method. Called by orchestrator.
        """
        logger.info("Pre-Processor starting...")
        
        pdf_count = 0
        all_tickers = [self.focal_company] + self.peer_comps if self.focal_company else self.peer_comps
        for t in all_tickers:
            ticker_dir = self.input_path / t
            if ticker_dir.exists():
                pdf_count += len(list(ticker_dir.rglob("*.pdf")))
        
        with Progress() as progress:
            task = progress.add_task("[cyan]Processing documents...", total=pdf_count)
            
            if self.focal_company:
                self.process_company(self.focal_company, True, progress, task)
                
            for peer in self.peer_comps:
                self.process_company(peer, False, progress, task)
                
        if self.focal_company:
            self.merge_financials(self.focal_company)
        for peer in self.peer_comps:
            self.merge_financials(peer)
            
        self.build_all_context_packages({})
        self.save_log()
        
        logger.info("Pre-Processor complete. Context packages ready for all 13 agents.")
