import os
import json

class ContextBroker:
    def __init__(self, focal_company: str, processed_dir: str):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.base_path = os.path.join(base_dir, processed_dir, focal_company)
        self.context_packages_dir = os.path.join(self.base_path, "context_packages")

    def write(self, agent_id: str, findings: dict) -> None:
        os.makedirs(self.context_packages_dir, exist_ok=True)
        out_file = os.path.join(self.context_packages_dir, f"{agent_id}_findings.json")
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(findings, f, indent=2)

    def read(self, agent_id: str) -> dict:
        in_file = os.path.join(self.context_packages_dir, f"{agent_id}_findings.json")
        if not os.path.isfile(in_file):
            return {}
        try:
            with open(in_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def read_many(self, agent_ids: list[str]) -> dict:
        result = {}
        for agent_id in agent_ids:
            result[agent_id] = self.read(agent_id)
        return result
