import os
import json
from abc import ABC, abstractmethod
from llm.client import BaseLLMClient

class BaseAgent(ABC):
    def __init__(self, agent_id: str, config: dict, llm_client: BaseLLMClient):
        self.agent_id = agent_id
        self.config = config
        self.llm_client = llm_client
        
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        prompts_dir = config.get("paths", {}).get("prompts_dir", "templates/prompts")
        prompt_path = os.path.join(base_dir, prompts_dir, f"{agent_id}_prompt.txt")
        
        if not os.path.isfile(prompt_path):
            raise FileNotFoundError(f"Prompt file missing: {prompt_path}")
            
        with open(prompt_path, "r", encoding="utf-8") as f:
            self.prompt_template = f.read()

    def load_context(self, context_package: dict) -> str:
        return json.dumps(context_package, indent=2)

    # Note: subagents that read/write the context broker override run() with an additional broker parameter
    @abstractmethod
    def run(self, context_package: dict) -> dict:
        pass

    def save_output(self, result: dict) -> None:
        focal_company = self.config.get("run", {}).get("focal_company", "unknown_company")
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        processed_dir = self.config.get("paths", {}).get("processed_dir", "processed")
        
        out_dir = os.path.join(base_dir, processed_dir, focal_company, "frameworks")
        os.makedirs(out_dir, exist_ok=True)
        
        out_file = os.path.join(out_dir, f"{self.agent_id}.json")
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
