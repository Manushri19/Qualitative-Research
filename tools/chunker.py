import json
from pathlib import Path
from typing import List, Dict, Tuple

class SemanticChunker:
    """
    Takes extracted text and breaks it into overlapping chunks,
    then tags each chunk with relevant topic labels using a hybrid approach:
    keyword-based first, ambiguous chunks flagged.
    """
    TOPIC_KEYWORDS = {
        "financials": [
            "revenue", "profit", "ebitda", "margin", "roe",
            "roce", "roic", "wacc", "earnings", "cash flow",
            "balance sheet", "debt", "equity", "capex",
            "depreciation", "tax", "dividend", "eps"
        ],
        "strategy": [
            "strategy", "strategic", "vision", "mission",
            "growth", "expansion", "plan", "initiative",
            "objective", "goal", "priority", "focus area",
            "roadmap", "outlook"
        ],
        "competition": [
            "competitor", "competition", "market share",
            "peer", "industry", "rival", "differentiat",
            "competitive advantage", "positioning", "moat"
        ],
        "regulation": [
            "regulation", "regulatory", "compliance",
            "government", "policy", "sebi", "rbi", "gst",
            "tax policy", "antitrust", "license", "patent",
            "tariff", "trade"
        ],
        "suppliers": [
            "supplier", "vendor", "procurement", "raw material",
            "input cost", "supply chain", "sourcing"
        ],
        "customers": [
            "customer", "client", "buyer", "consumer",
            "demand", "retention", "acquisition", "churn",
            "satisfaction", "loyalty", "switching"
        ],
        "innovation": [
            "innovation", "technology", "digital", "r&d",
            "research", "disrupt", "new product", "launch",
            "patent", "intellectual property", "ai", "automation"
        ],
        "brand": [
            "brand", "reputation", "perception", "awareness",
            "premium", "prestige", "trust", "recall"
        ],
        "capex": [
            "capital expenditure", "capex", "investment",
            "plant", "equipment", "infrastructure", "capacity",
            "expansion", "asset"
        ]
    }

    def __init__(self, chunk_size: int = 800, overlap: int = 100):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, text: str, source_file: str, doc_type: str) -> List[Dict]:
        """
        Splits text into overlapping chunks of chunk_size words
        with overlap words of overlap between chunks.
        """
        words = text.split()
        chunks = []
        
        if not words:
            return chunks

        i = 0
        index = 0
        step = self.chunk_size - self.overlap
        
        # Safeguard against zero or negative step
        if step <= 0:
            step = self.chunk_size
            
        while i < len(words):
            chunk_words = words[i:i + self.chunk_size]
            chunk_text = " ".join(chunk_words)
            tags, ambiguous = self.tag_chunk(chunk_text)
            
            chunks.append({
                "chunk_id": f"{source_file}_{index}",
                "source_file": source_file,
                "doc_type": doc_type,
                "text": chunk_text,
                "word_count": len(chunk_words),
                "tags": tags,
                "ambiguous": ambiguous
            })
            
            index += 1
            i += step
            
        return chunks

    def tag_chunk(self, chunk_text: str) -> Tuple[List[str], bool]:
        """
        Lowercases chunk text.
        Checks against each topic in TOPIC_KEYWORDS.
        If any keyword from a topic found in chunk → add topic tag.
        Returns (tags_list, ambiguous)
        ambiguous = True if len(tags_list) < 2
        """
        text_lower = chunk_text.lower()
        tags_list = []
        
        for topic, keywords in self.TOPIC_KEYWORDS.items():
            for kw in keywords:
                if kw in text_lower:
                    tags_list.append(topic)
                    break
                    
        ambiguous = len(tags_list) < 2
        return tags_list, ambiguous

    def save_chunks(self, chunks: List[Dict], output_path: Path) -> None:
        """Saves chunks list as chunks.json"""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(chunks, f, indent=2)
