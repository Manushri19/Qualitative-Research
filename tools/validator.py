import os
import requests
from dotenv import load_dotenv

def validate(config: dict) -> tuple[bool, str]:
    run_config = config.get("run", {})
    focal_company = run_config.get("focal_company")
    peer_comps = run_config.get("peer_comps")
    
    # CHECK 1 — focal_company not empty
    if not focal_company:
        return False, "config.yaml error: focal_company is not set."
        
    # CHECK 2 — peer_comps not empty
    if not peer_comps:
        return False, "config.yaml error: peer_comps list is empty."
        
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    input_dir = os.path.join(base_dir, "input")
    
    # CHECK 3 — focal_company folder exists in /input/
    focal_path = os.path.join(input_dir, focal_company)
    if not os.path.isdir(focal_path):
        return False, (f"Hard Stop: Folder /input/{focal_company}/ not found.\n"
                       f"Please create it and add company documents before running.")
        
    # CHECK 4 — each peer_comp folder exists in /input/
    for peer in peer_comps:
        peer_path = os.path.join(input_dir, peer)
        if not os.path.isdir(peer_path):
            return False, (f"Hard Stop: Folder /input/{peer}/ not found.\n"
                           f"Please create it and add company documents before running.")
            
    # CHECK 5 — no undeclared folders in /input/
    if os.path.exists(input_dir):
        declared_folders = [focal_company] + peer_comps
        for item in os.listdir(input_dir):
            item_path = os.path.join(input_dir, item)
            if os.path.isdir(item_path):
                if item not in declared_folders:
                    return False, (f"Hard Stop: Found /input/{item}/ which is\n"
                                   f"not declared in config.yaml as focal_company or peer_comp.\n"
                                   f"Please update config.yaml to include it or remove the folder\n"
                                   f"before proceeding.")
                    
    # CHECK 6 — output_dir is set
    output_config = config.get("output", {})
    report_dir = output_config.get("report_dir")
    if not report_dir:
        return False, "config.yaml error: output report_dir is not set."
        
    # CHECK 7 — Ollama health check
    load_dotenv()
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    model_name = config.get("model", {}).get("model_name", "")
    
    try:
        response = requests.get(f"{ollama_base_url}/api/tags", timeout=5)
    except (requests.ConnectionError, requests.Timeout):
        return False, (f"Hard Stop: Ollama is not reachable at \n"
                       f"{ollama_base_url}. Please ensure Ollama is running \n"
                       f"before starting the pipeline.")
                       
    if response.status_code != 200:
        return False, (f"Hard Stop: Ollama returned status \n"
                       f"{response.status_code}. Please check Ollama is running correctly.")
                       
    tags_data = response.json()
    available_models = [model.get("name") for model in tags_data.get("models", [])]
    
    if model_name not in available_models and f"{model_name}:latest" not in available_models:
        return False, (f"Hard Stop: Model {model_name} is not \n"
                       f"found in Ollama. Please run:\n"
                       f"ollama pull {model_name}\n"
                       f"before starting the pipeline.")
                       
    return True, "All validation checks passed."
