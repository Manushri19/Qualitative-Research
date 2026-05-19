import json
import os
from pathlib import Path
from typing import List, Dict, Any

class ContextBuilder:
    """
    Assembles the pre-built context package for each of the 13 subagents
    by selecting and ranking the most relevant chunks and data,
    enforcing a token budget per package.
    """
    AGENT_TAG_RELEVANCE = {
        "F01": {"primary": ["financials"], "secondary": ["strategy"]},
        "F02": {"primary": ["financials", "strategy"], "secondary": ["competition"]},
        "F03": {"primary": ["competition"], "secondary": ["financials", "strategy"]},
        "F04": {"primary": ["suppliers", "customers"], "secondary": ["competition", "strategy"]},
        "F05": {"primary": ["competition", "regulation"], "secondary": ["capex", "innovation"]},
        "F06": {"primary": ["competition", "financials"], "secondary": ["strategy", "capex"]},
        "F07": {"primary": ["innovation", "strategy"], "secondary": ["competition"]},
        "F08a": {"primary": ["customers", "brand", "innovation"], "secondary": ["strategy", "competition"]},
        "F08b": {"primary": ["financials", "capex"], "secondary": ["suppliers", "strategy"]},
        "F08c": {"primary": ["financials", "competition", "strategy"], "secondary": ["customers", "brand", "capex"]},
        "F09": {"primary": ["regulation"], "secondary": ["strategy", "financials"]},
        "F10": {"primary": ["competition", "strategy"], "secondary": ["financials", "capex"]},
        "F11": {"primary": ["brand", "customers"], "secondary": ["strategy", "innovation"]}
    }

    TOKEN_BUDGETS = {
        "financials": 40000,
        "peer_financials": 20000,
        "narrative": 60000,
        "peer_narrative": 20000,
        "broker_findings": 8000,
        "headroom": 10000
    }

    def __init__(self, config: dict):
        self.config = config
        self.processed_dir = config.get("paths", {}).get("processed_dir", "processed")
        self.focal_company = config.get("run", {}).get("focal_company", "")
        self.peer_comps = config.get("run", {}).get("peer_comps", [])

    def estimate_tokens(self, text: str) -> int:
        """
        Estimates token count as: len(text.split()) * 1.35
        This is a safe approximation for English financial text.
        """
        if not text:
            return 0
        return int(len(text.split()) * 1.35)

    def score_chunks(self, chunks: List[Dict], agent_id: str) -> List[Dict]:
        """
        Scores each chunk by relevance to agent_id.
        Scoring rules:
        - Primary tag match: +2 points per matching tag
        - Secondary tag match: +1 point per matching tag
        - No match: 0 points
        - ambiguous chunk: -1 point penalty
        Returns chunks sorted by score descending.
        """
        relevance = self.AGENT_TAG_RELEVANCE.get(agent_id, {"primary": [], "secondary": []})
        primary_set = set(relevance.get("primary", []))
        secondary_set = set(relevance.get("secondary", []))

        for c in chunks:
            score = 0
            tags_set = set(c.get("tags", []))
            
            score += 2 * len(tags_set.intersection(primary_set))
            score += 1 * len(tags_set.intersection(secondary_set))
            
            if c.get("ambiguous", False):
                score -= 1
                
            c["relevance_score"] = score

        return sorted(chunks, key=lambda x: x.get("relevance_score", 0), reverse=True)

    def select_chunks_within_budget(self, chunks: List[Dict], token_budget: int) -> List[Dict]:
        """
        Iterates sorted chunks.
        Adds chunk to selection if cumulative token estimate stays within token_budget.
        Stops when budget would be exceeded.
        Returns selected chunks list.
        """
        selected = []
        current_tokens = 0
        
        for c in chunks:
            text = c.get("text", "")
            est = self.estimate_tokens(text)
            if current_tokens + est <= token_budget:
                selected.append(c)
                current_tokens += est
            else:
                break
                
        return selected

    def build(self, agent_id: str, broker_findings: dict) -> dict:
        """
        Assembles complete context package for agent_id.
        """
        base_dir = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        processed_path = base_dir / self.processed_dir
        focal_path = processed_path / self.focal_company

        # STEP 1: Load focal yearly_master.json + quarterly_master.json
        focal_financials = {"yearly": {}, "quarterly": {}}
        yearly_path = focal_path / "financials" / "yearly_master.json"
        quarterly_path = focal_path / "financials" / "quarterly_master.json"
        
        if yearly_path.exists():
            with open(yearly_path, 'r', encoding='utf-8') as f:
                focal_financials["yearly"] = json.load(f)
        if quarterly_path.exists():
            with open(quarterly_path, 'r', encoding='utf-8') as f:
                focal_financials["quarterly"] = json.load(f)
                
        fin_tokens = self.estimate_tokens(json.dumps(focal_financials))

        # STEP 2: Load all peer yearly_master.json files
        peer_financials = {}
        for peer in self.peer_comps:
            peer_y_path = focal_path / "financials" / "peers" / peer / "yearly_master.json"
            if peer_y_path.exists():
                with open(peer_y_path, 'r', encoding='utf-8') as f:
                    peer_financials[peer] = json.load(f)
                    
        peer_fin_tokens = self.estimate_tokens(json.dumps(peer_financials))

        # STEP 3: Load all focal tagged chunks
        focal_chunks = []
        focal_tagged_dir = focal_path / "tagged_chunks"
        if focal_tagged_dir.exists():
            for chunk_file in focal_tagged_dir.rglob("chunks.json"):
                with open(chunk_file, 'r', encoding='utf-8') as f:
                    focal_chunks.extend(json.load(f))
                    
        scored_focal = self.score_chunks(focal_chunks, agent_id)
        selected_focal = self.select_chunks_within_budget(scored_focal, self.TOKEN_BUDGETS["narrative"])
        narrative_tokens = sum(self.estimate_tokens(c.get("text", "")) for c in selected_focal)

        # STEP 4: Load all peer tagged chunks
        peer_chunks = []
        for peer in self.peer_comps:
            peer_tagged_dir = processed_path / peer / "tagged_chunks"
            if peer_tagged_dir.exists():
                for chunk_file in peer_tagged_dir.rglob("chunks.json"):
                    with open(chunk_file, 'r', encoding='utf-8') as f:
                        p_chunks = json.load(f)
                        for c in p_chunks:
                            c["peer"] = peer
                        peer_chunks.extend(p_chunks)
                        
        scored_peer = self.score_chunks(peer_chunks, agent_id)
        selected_peer = self.select_chunks_within_budget(scored_peer, self.TOKEN_BUDGETS["peer_narrative"])
        peer_narrative_tokens = sum(self.estimate_tokens(c.get("text", "")) for c in selected_peer)

        # STEP 5: Include broker_findings within broker budget
        broker_tokens = self.estimate_tokens(json.dumps(broker_findings))

        # Format chunks for the final package
        formatted_focal = [
            {
                "source": c.get("source_file", ""),
                "doc_type": c.get("doc_type", ""),
                "text": c.get("text", ""),
                "tags": c.get("tags", []),
                "relevance_score": c.get("relevance_score", 0)
            } for c in selected_focal
        ]
        
        formatted_peer = [
            {
                "source": c.get("source_file", ""),
                "peer": c.get("peer", ""),
                "doc_type": c.get("doc_type", ""),
                "text": c.get("text", ""),
                "tags": c.get("tags", []),
                "relevance_score": c.get("relevance_score", 0)
            } for c in selected_peer
        ]

        # STEP 6: Assemble final package dict
        total_tokens = fin_tokens + peer_fin_tokens + narrative_tokens + peer_narrative_tokens + broker_tokens
        
        package = {
            "agent_id": agent_id,
            "focal_company": self.focal_company,
            "peer_comps": self.peer_comps,
            "financials": {
                "yearly": focal_financials.get("yearly", {}),
                "quarterly": focal_financials.get("quarterly", {})
            },
            "peer_financials": peer_financials,
            "narrative_chunks": formatted_focal,
            "peer_narrative_chunks": formatted_peer,
            "broker_findings": broker_findings,
            "token_estimates": {
                "financials": fin_tokens,
                "peer_financials": peer_fin_tokens,
                "narrative": narrative_tokens,
                "peer_narrative": peer_narrative_tokens,
                "broker_findings": broker_tokens,
                "total": total_tokens
            }
        }

        # STEP 7: Rebalance package
        package = self.rebalance_package(package)
        
        # STEP 8: Save to /processed/{focal}/context_packages/{agent_id}_context.json
        out_path = focal_path / "context_packages" / f"{agent_id}_context.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(package, f, indent=2)

        return package

    def summarise_financials(self, financial_data: dict, budget: int) -> dict:
        """
        Called when token estimate for financial_data exceeds budget.
        """
        from llm.client import get_llm_client
        import logging
        client = get_llm_client(self.config)
        
        system_prompt = "You are a financial data compressor. Your only job is to extract and preserve key metrics."
        user_prompt = f"""Compress these financial statements into a compact
markdown table preserving ONLY these metrics per 
fiscal year: Revenue, EBITDA, PAT, ROCE, ROIC,
Debt/Equity ratio, Capex.
Output ONLY the markdown table. No commentary.

Data:
{json.dumps(financial_data)}"""

        original_tokens = self.estimate_tokens(json.dumps(financial_data))
        compressed_text = ""
        
        for _ in range(3):
            try:
                compressed_text = client.complete(system=system_prompt, prompt=user_prompt)
                if compressed_text.strip():
                    break
            except Exception as e:
                logging.error(f"Error summarising financials: {e}")
                
        compressed_tokens = self.estimate_tokens(compressed_text)
        agent_id = self.config.get('agent_id', 'agent')
        logging.info(f"Financials summarised for {agent_id}: {original_tokens} -> {compressed_tokens} tokens")
        
        return {
            "compressed_table": compressed_text, 
            "compression_note": "Summarised to retain key metrics due to token limits."
        }

    def progressive_chunk_drop(self, chunks: list[dict], budget: int) -> list[dict]:
        import logging
        
        def recheck(current_chunks):
            return sum(self.estimate_tokens(c["text"]) for c in current_chunks)
            
        current_tokens = recheck(chunks)
        if current_tokens <= budget:
            return chunks
            
        # PASS 1
        pass1 = [c for c in chunks if not c.get("ambiguous", False)]
        logging.info(f"Pass 1: dropped {len(chunks)-len(pass1)}, tokens {recheck(pass1)}")
        if recheck(pass1) <= budget: return pass1
        
        # PASS 2
        pass2 = [c for c in pass1 if c.get("relevance_score", 0) > 0]
        logging.info(f"Pass 2: dropped {len(pass1)-len(pass2)}, tokens {recheck(pass2)}")
        if recheck(pass2) <= budget: return pass2
        
        # PASS 3
        pass3 = sorted(pass2, key=lambda x: x.get("relevance_score", 0), reverse=True)
        while len(pass3) > 10 and recheck(pass3) > budget:
            pass3.pop()
            
        min_score = pass3[-1].get("relevance_score", 0) if pass3 else 0
        logging.info(f"Pass 3: dropped {len(pass2)-len(pass3)}, tokens {recheck(pass3)}, min_score {min_score}")
        if recheck(pass3) <= budget: return pass3
        
        # PASS 4
        combined_text = "\n\n".join([c["text"] for c in pass3])
        from llm.client import get_llm_client
        client = get_llm_client(self.config)
        sys_prompt = "You are a text compressor. Summarise the following text preserving key factual details."
        user_prompt = f"Summarise the following text compactly within {budget} tokens:\n{combined_text}"
        
        summary = ""
        for _ in range(3):
            try:
                summary = client.complete(system=sys_prompt, prompt=user_prompt)
                if summary.strip():
                    break
            except Exception:
                pass
                
        logging.info(f"Pass 4: summarised chunks into single string.")
        return [{
            "source": "summarised_chunks",
            "doc_type": "summary",
            "text": summary,
            "tags": [],
            "relevance_score": min_score
        }]

    def rebalance_package(self, package: dict, total_budget: int = 158000) -> dict:
        import logging
        total = package.get("token_estimates", {}).get("total", 0)
        
        package["rebalancing_applied"] = False
        package["rebalancing_log"] = []
        
        if total <= total_budget:
            return package
            
        agent_id = package.get("agent_id", "Unknown")
        rebalance_log = []
        package["rebalancing_applied"] = True
        
        # STEP 1
        pn_chunks = package.get("peer_narrative_chunks", [])
        if pn_chunks:
            orig_tokens = sum(self.estimate_tokens(c["text"]) for c in pn_chunks)
            budget = self.TOKEN_BUDGETS["peer_narrative"] // 2
            new_chunks = self.progressive_chunk_drop(pn_chunks, budget)
            package["peer_narrative_chunks"] = new_chunks
            new_tokens = sum(self.estimate_tokens(c["text"]) for c in new_chunks)
            rebalance_log.append({
                "bucket": "peer_narrative_chunks",
                "original_tokens": orig_tokens,
                "budget": budget,
                "strategy_applied": "progressive_chunk_drop",
                "final_tokens": new_tokens,
                "data_loss": True,
                "data_loss_note": None
            })
            
        # STEP 2
        q_fin = package.get("financials", {}).get("quarterly", {})
        if q_fin:
            orig_tokens = self.estimate_tokens(json.dumps(q_fin))
            budget = self.TOKEN_BUDGETS["financials"] // 4
            q_sum = self.summarise_financials(q_fin, budget)
            package["financials"]["quarterly"] = q_sum
            new_tokens = self.estimate_tokens(json.dumps(q_sum))
            rebalance_log.append({
                "bucket": "financials_quarterly",
                "original_tokens": orig_tokens,
                "budget": budget,
                "strategy_applied": "summarise_financials",
                "final_tokens": new_tokens,
                "data_loss": True,
                "data_loss_note": None
            })
            
        # STEP 3
        p_fin = package.get("peer_financials", {})
        for peer, fin_data in p_fin.items():
            orig_tokens = self.estimate_tokens(json.dumps(fin_data))
            budget = self.TOKEN_BUDGETS["peer_financials"] // max(1, len(p_fin))
            p_sum = self.summarise_financials(fin_data, budget)
            package["peer_financials"][peer] = p_sum
            new_tokens = self.estimate_tokens(json.dumps(p_sum))
            rebalance_log.append({
                "bucket": f"peer_financials_{peer}",
                "original_tokens": orig_tokens,
                "budget": budget,
                "strategy_applied": "summarise_financials",
                "final_tokens": new_tokens,
                "data_loss": True,
                "data_loss_note": None
            })
            
        # STEP 4
        n_chunks = package.get("narrative_chunks", [])
        if n_chunks:
            orig_tokens = sum(self.estimate_tokens(c["text"]) for c in n_chunks)
            budget = self.TOKEN_BUDGETS["narrative"] // 2
            new_chunks = self.progressive_chunk_drop(n_chunks, budget)
            package["narrative_chunks"] = new_chunks
            new_tokens = sum(self.estimate_tokens(c["text"]) for c in new_chunks)
            rebalance_log.append({
                "bucket": "narrative_chunks",
                "original_tokens": orig_tokens,
                "budget": budget,
                "strategy_applied": "progressive_chunk_drop",
                "final_tokens": new_tokens,
                "data_loss": True,
                "data_loss_note": None
            })
            
        # Recalculate
        fin_tokens = self.estimate_tokens(json.dumps(package.get("financials", {})))
        pfin_tokens = self.estimate_tokens(json.dumps(package.get("peer_financials", {})))
        n_tokens = sum(self.estimate_tokens(c["text"]) for c in package.get("narrative_chunks", []))
        pn_tokens = sum(self.estimate_tokens(c["text"]) for c in package.get("peer_narrative_chunks", []))
        br_tokens = self.estimate_tokens(json.dumps(package.get("broker_findings", {})))
        
        new_total = fin_tokens + pfin_tokens + n_tokens + pn_tokens + br_tokens
        package["token_estimates"] = {
            "financials": fin_tokens,
            "peer_financials": pfin_tokens,
            "narrative": n_tokens,
            "peer_narrative": pn_tokens,
            "broker_findings": br_tokens,
            "total": new_total
        }
        package["rebalancing_log"] = rebalance_log
        
        # STEP 5
        if new_total > total_budget:
            logging.critical(f"Package {agent_id} could not fit within {total_budget} token budget after all compression strategies. Final size: {new_total} tokens. Proceeding with oversized package — monitor for LLM context errors.")
            
        return package
