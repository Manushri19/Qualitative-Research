import os
from abc import ABC, abstractmethod
# pyrefly: ignore [missing-import]
import ollama

class BaseLLMClient(ABC):
    def __init__(self, model_name: str, context_window: int, temperature: float, max_tokens: int):
        self.model_name = model_name
        self.context_window = context_window
        self.temperature = temperature
        self.max_tokens = max_tokens

    @abstractmethod
    def complete(self, system: str, prompt: str) -> str:
        pass

class OllamaClient(BaseLLMClient):
    def __init__(self, model_name: str, context_window: int, temperature: float, max_tokens: int):
        super().__init__(model_name, context_window, temperature, max_tokens)
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.client = ollama.Client(host=self.base_url)

    def complete(self, system: str, prompt: str) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}
        ]
        options = {
            "temperature": self.temperature,
            "num_predict": self.max_tokens,
            "num_ctx": self.context_window
        }
        try:
            response = self.client.chat(model=self.model_name, messages=messages, options=options)
            return response.get("message", {}).get("content", "")
        except Exception as e:
            raise RuntimeError(f"Ollama call failed: {str(e)}") from e

def get_llm_client(config: dict) -> BaseLLMClient:
    model_config = config.get("model", {})
    provider = model_config.get("provider", "")
    model_name = model_config.get("model_name", "")
    context_window = model_config.get("context_window", 8000)
    temperature = model_config.get("temperature", 0.0)
    max_tokens = model_config.get("max_tokens", 2000)

    if provider == "ollama":
        return OllamaClient(model_name, context_window, temperature, max_tokens)
    else:
        raise NotImplementedError(
            f"Provider {provider} is not yet supported.\n"
            "Only ollama is supported in this version."
        )
