import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

import fitz  # PyMuPDF
from llama_parse import LlamaParse
from unstructured.partition.pdf import partition_pdf

class PageMapper:
    """
    Uses PyMuPDF to scan annual report PDFs and detect physical page ranges 
    for high-signal sections using keyword matching.
    """
    def __init__(self):
        self.SECTION_KEYWORDS = {
            "mda": [
                "management discussion",
                "management's discussion",
                "discussion and analysis",
                "managements discussion"
            ],
            "business_overview": [
                "business overview",
                "business review",
                "our business",
                "company overview"
            ],
            "management_commentary": [
                "chairman's letter",
                "chairman's message",
                "managing director",
                "letter to shareholders",
                "dear shareholders",
                "dear stakeholder"
            ],
            "segment_discussion": [
                "segment report",
                "segment information",
                "segment revenue",
                "segment result",
                "business segment"
            ]
        }

    def build_page_map(self, pdf_path: Path) -> dict:
        doc = fitz.open(str(pdf_path))
        total_physical_pages = len(doc)
        empty_pages = 0
        
        keyword_matches = {k: [] for k in self.SECTION_KEYWORDS}
        
        for page_num in range(total_physical_pages):
            page = doc[page_num]
            text = page.get_text()[:300].lower()
            if not text.strip():
                empty_pages += 1
                continue
                
            for section, keywords in self.SECTION_KEYWORDS.items():
                for kw in keywords:
                    if kw in text:
                        keyword_matches[section].append(page_num)
                        break 
                        
        is_scanned_pdf = False
        if total_physical_pages > 0:
            is_scanned_pdf = (empty_pages / total_physical_pages) > 0.30
            
        detected_sections = {
            "mda": None,
            "business_overview": None,
            "management_commentary": None,
            "segment_discussion": None
        }
        
        toc_limit = max(1, int(total_physical_pages * 0.05))
        
        start_pages = {}
        for section, matches in keyword_matches.items():
            if not matches:
                logging.warning(f"Section {section} not detected in {pdf_path.name}")
                continue
                
            if len(matches) == 1:
                start_pages[section] = matches[0]
            else:
                first_match = matches[0]
                if first_match < toc_limit:
                    start_pages[section] = matches[-1]
                else:
                    start_pages[section] = first_match

        sorted_sections = sorted([(k, v) for k, v in start_pages.items()], key=lambda x: x[1])
        
        for i, (section, start_page) in enumerate(sorted_sections):
            if i + 1 < len(sorted_sections):
                end_page = sorted_sections[i+1][1] - 1
            else:
                end_page = total_physical_pages - 1
                
            if end_page < start_page:
                end_page = start_page 
                
            detected_sections[section] = {"start": start_page, "end": end_page}
            
        num_detected = len(start_pages)
        if num_detected == 4:
            detection_confidence = "full"
        elif num_detected > 0:
            detection_confidence = "partial"
        else:
            detection_confidence = "none"

        doc.close()

        return {
            "total_physical_pages": total_physical_pages,
            "detected_sections": detected_sections,
            "is_scanned_pdf": is_scanned_pdf,
            "detection_confidence": detection_confidence
        }

    def save_page_map(self, page_map: dict, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(page_map, f, indent=2)


class AnnualReportExtractor:
    """
    Extracts only high-signal sections from full annual reports using page_map.
    Uses LlamaParse premium mode.
    """
    def __init__(self, api_key: str, parse_mode: str):
        self.parser = LlamaParse(
            api_key=api_key,
            result_type="markdown",
            premium_mode=True,
            language="en"
        )

    def extract(self, pdf_path: Path, page_map: dict, output_dir: Path) -> dict:
        output_dir.mkdir(parents=True, exist_ok=True)
        extracted_sections = []
        
        is_scanned = page_map.get("is_scanned_pdf", False)
        conf = page_map.get("detection_confidence", "none")
        
        if is_scanned or conf == "none":
            logging.info(f"Falling back to full extraction for {pdf_path.name}")
            docs = self.parser.load_data(str(pdf_path))
            full_text = "\n\n".join([doc.text for doc in docs])
            
            with open(output_dir / "full_fallback.txt", "w", encoding="utf-8") as f:
                f.write(full_text)
                
            return {
                "status": "fallback",
                "extracted_sections": [],
                "fallback_used": True,
                "output_dir": str(output_dir)
            }
            
        doc = fitz.open(str(pdf_path))
        for section_name, limits in page_map["detected_sections"].items():
            if limits is None:
                logging.warning(f"Section {section_name} not detected in {pdf_path.name}, skipping.")
                continue
                
            start = limits["start"]
            end = limits["end"]
            
            temp_pdf = output_dir / f"temp_{section_name}.pdf"
            doc_section = fitz.open()
            doc_section.insert_pdf(doc, from_page=start, to_page=end)
            doc_section.save(temp_pdf)
            doc_section.close()
            
            docs = self.parser.load_data(str(temp_pdf))
            section_text = "\n\n".join([d.text for d in docs])
            
            with open(output_dir / f"{section_name}.txt", "w", encoding="utf-8") as f:
                f.write(section_text)
                
            temp_pdf.unlink()
            extracted_sections.append(section_name)
            
        doc.close()
        
        return {
            "status": "success" if len(extracted_sections) == 4 else "partial",
            "extracted_sections": extracted_sections,
            "fallback_used": False,
            "output_dir": str(output_dir)
        }


class ExchangeFilingExtractor:
    """
    Extracts financial statements from short exchange filing PDFs.
    Uses LlamaParse standard mode. Saves output as JSON and Markdown.
    """
    def __init__(self, api_key: str, parse_mode: str):
        self.parser = LlamaParse(
            api_key=api_key,
            result_type="markdown",
            premium_mode=False,
            language="en"
        )

    def extract(self, pdf_path: Path, output_dir: Path) -> dict:
        output_dir.mkdir(parents=True, exist_ok=True)
        docs = self.parser.load_data(str(pdf_path))
        full_text = "\n\n".join([d.text for d in docs])
        
        yearly_keywords = ["annual", "year ended", "twelve months", "fy"]
        quarterly_keywords = ["quarter", "three months", "q1", "q2", "q3", "q4"]
        
        lines = full_text.split('\n')
        tables = []
        current_table = []
        context = ""
        
        for i, line in enumerate(lines):
            if line.strip().startswith('|'):
                if not current_table:
                    start_ctx = max(0, i - 3)
                    context = " ".join(lines[start_ctx:i]).lower()
                current_table.append(line)
            else:
                if current_table:
                    tables.append({"context": context, "lines": current_table})
                    current_table = []
                    context = ""
        if current_table:
            tables.append({"context": context, "lines": current_table})
            
        yearly_tables = []
        quarterly_tables = []
        
        for i, tbl in enumerate(tables):
            ctx = tbl["context"]
            is_quarterly = any(kw in ctx for kw in quarterly_keywords)
            is_yearly = any(kw in ctx for kw in yearly_keywords)
            
            if (is_quarterly and is_yearly) or (not is_quarterly and not is_yearly):
                header = tbl["lines"][0].lower() if tbl["lines"] else ""
                is_q_header = any(kw in header for kw in quarterly_keywords)
                is_y_header = any(kw in header for kw in yearly_keywords)
                
                if is_q_header:
                    is_quarterly = True
                    is_yearly = False
                elif is_y_header:
                    is_yearly = True
                    is_quarterly = False
                else:
                    is_yearly = True
                    is_quarterly = False
                    
            parsed_table = {
                "table_name": f"Table_{i+1}",
                "headers": [],
                "rows": []
            }
            
            for r_idx, r_line in enumerate(tbl["lines"]):
                cols = [c.strip() for c in r_line.split('|')[1:-1]]
                if r_idx == 0:
                    parsed_table["headers"] = cols
                elif r_idx == 1 and all(c.replace('-', '').strip() == '' for c in cols):
                    continue 
                else:
                    if len(cols) > 0:
                        parsed_table["rows"].append({
                            "label": cols[0],
                            "values": cols[1:]
                        })
                        
            if is_quarterly:
                quarterly_tables.append(parsed_table)
            else:
                yearly_tables.append(parsed_table)
                
        yearly_extracted = len(yearly_tables) > 0
        quarterly_extracted = len(quarterly_tables) > 0
        
        if yearly_extracted:
            with open(output_dir / "financials_yearly.json", "w", encoding="utf-8") as f:
                json.dump({
                    "source_file": pdf_path.name,
                    "period": "yearly",
                    "tables": yearly_tables
                }, f, indent=2)
                
            yearly_md = []
            for t in yearly_tables:
                yearly_md.append(f"### {t['table_name']}")
                yearly_md.append("| " + " | ".join(t['headers']) + " |")
                yearly_md.append("|" + "|".join(["---"] * len(t['headers'])) + "|")
                for row in t['rows']:
                    yearly_md.append("| " + row['label'] + " | " + " | ".join(row['values']) + " |")
                yearly_md.append("\n")
                
            with open(output_dir / "financials_yearly.md", "w", encoding="utf-8") as f:
                f.write("\n".join(yearly_md))
                
        if quarterly_extracted:
            with open(output_dir / "financials_quarterly.json", "w", encoding="utf-8") as f:
                json.dump({
                    "source_file": pdf_path.name,
                    "period": "quarterly",
                    "tables": quarterly_tables
                }, f, indent=2)
                
            quarterly_md = []
            for t in quarterly_tables:
                quarterly_md.append(f"### {t['table_name']}")
                quarterly_md.append("| " + " | ".join(t['headers']) + " |")
                quarterly_md.append("|" + "|".join(["---"] * len(t['headers'])) + "|")
                for row in t['rows']:
                    quarterly_md.append("| " + row['label'] + " | " + " | ".join(row['values']) + " |")
                quarterly_md.append("\n")
                
            with open(output_dir / "financials_quarterly.md", "w", encoding="utf-8") as f:
                f.write("\n".join(quarterly_md))

        return {
            "status": "success" if (yearly_extracted or quarterly_extracted) else "failed",
            "yearly_extracted": yearly_extracted,
            "quarterly_extracted": quarterly_extracted,
            "output_dir": str(output_dir)
        }


class TranscriptExtractor:
    """
    Extracts full text from earnings call transcripts using Unstructured.io (free, local).
    """
    def __init__(self):
        pass

    def extract(self, pdf_path: Path, output_dir: Path) -> dict:
        output_dir.mkdir(parents=True, exist_ok=True)
        elements = partition_pdf(filename=str(pdf_path))
        full_text = "\n".join([str(e) for e in elements])
        
        output_path = output_dir / "full_text.txt"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(full_text)
            
        doc = fitz.open(str(pdf_path))
        page_count = len(doc)
        doc.close()
            
        return {
            "status": "success",
            "page_count": page_count,
            "char_count": len(full_text),
            "output_path": str(output_path)
        }


class PresentationExtractor:
    """
    Extracts full text from investor presentations using LlamaParse premium mode.
    """
    def __init__(self, api_key: str):
        self.parser = LlamaParse(
            api_key=api_key,
            result_type="markdown",
            premium_mode=True,
            language="en"
        )

    def extract(self, pdf_path: Path, output_dir: Path) -> dict:
        output_dir.mkdir(parents=True, exist_ok=True)
        docs = self.parser.load_data(str(pdf_path))
        full_text = "\n\n".join([d.text for d in docs])
        
        output_path = output_dir / "full_text.txt"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(full_text)
            
        return {
            "status": "success",
            "output_path": str(output_path)
        }
