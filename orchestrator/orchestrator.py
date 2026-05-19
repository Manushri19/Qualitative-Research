import json
from pathlib import Path
from loguru import logger
import concurrent.futures
from typing import Any

from llm.client import BaseLLMClient
from orchestrator.context_broker import ContextBroker
from preprocessor.preprocessor import PreProcessor
from tools.report_assembler import ReportAssembler

from subagents.f01_introduction import F01IntroductionAgent
from subagents.f02_why_strategy import F02WhyStrategyAgent
from subagents.f03_lay_of_the_land import F03LayOfTheLandAgent
from subagents.f04_three_forces import F04ThreeForcesAgent
from subagents.f05_new_entrants import F05NewEntrantsAgent
from subagents.f06_rivalry import F06RivalryAgent
from rich.console import Console

class Orchestrator:
    def __init__(self, config: dict, llm_client: BaseLLMClient):
        self.config = config
        self.llm_client = llm_client
        
        self.focal_company = self.config.get("run", {}).get("focal_company", "unknown")
        processed_dir = self.config.get("paths", {}).get("processed_dir", "processed")
        self.context_broker = ContextBroker(self.focal_company, processed_dir)

    def _load_context_package(self, agent_id: str) -> dict:
        path = Path(self.config.get("paths", {}).get("processed_dir", "processed")) / self.focal_company / "context_packages" / f"{agent_id}.json"
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
        
    def _run_agent(self, agent_class, session: dict, broker: ContextBroker):
        agent = agent_class(self.config, self.llm_client, session)
        context = self._load_context_package(agent.agent_id)
        if agent.agent_id == "F01":
            result = agent.run(context)
        else:
            result = agent.run(context, broker)
        broker.write(agent.agent_id, result)
        return result

    def run(self, session: dict) -> None:
        """
        Master pipeline orchestrator.
        Runs all phases in sequence.
        Phase A agents run in parallel using concurrent.futures.ThreadPoolExecutor.
        Phase B agents run in parallel.
        Report assembly runs last sequentially.
        """
        console = Console()
        
        # PHASE 0: Pre-Processor (Already done, skipping for direct qualitative/synthesis run)
        # preprocessor = PreProcessor(self.config)
        # preprocessor.run()
        # logger.info("Phase 0 complete — context packages ready")
        
        # PHASE A: Parallel — F01, F02, F03
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(self._run_agent, F01IntroductionAgent, session, self.context_broker): "F01",
                executor.submit(self._run_agent, F02WhyStrategyAgent, session, self.context_broker): "F02",
                executor.submit(self._run_agent, F03LayOfTheLandAgent, session, self.context_broker): "F03"
            }
            for future in concurrent.futures.as_completed(futures):
                agent_id = futures[future]
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"{agent_id} failed in Phase A: {e}")
                    
        logger.info("Phase A complete — F01, F02, F03 done")
        
        # PHASE B: Sequential then Parallel
        try:
            self._run_agent(F04ThreeForcesAgent, session, self.context_broker)
        except Exception as e:
            logger.error(f"F04 failed in Phase B: {e}")
            
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                executor.submit(self._run_agent, F05NewEntrantsAgent, session, self.context_broker): "F05",
                executor.submit(self._run_agent, F06RivalryAgent, session, self.context_broker): "F06"
            }
            for future in concurrent.futures.as_completed(futures):
                agent_id = futures[future]
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"{agent_id} failed in Phase B: {e}")
                    
        logger.info("Phase B complete — F04, F05, F06 done")
        
        # PHASE C: Report Assembly
        assembler = ReportAssembler(self.config, self.focal_company, session)
        output_path = assembler.assemble(self.context_broker, self.llm_client, session)
        
        logger.info(f"Pipeline complete. Report saved to: {output_path}")
        
        console.print("[bold green]✓ Research report generated[/bold green]")
        console.print(f"  {output_path}")
