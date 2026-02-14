"""
Ollama provider for local LLM inference
"""

import requests
from typing import Dict, Any, List


class OllamaProvider:
    """Ollama local LLM provider"""

    def __init__(self, host: str, model: str):
        self.host = host.rstrip('/')
        self.model = model

    def complete(
        self,
        *,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        seed: int
    ) -> Dict[str, Any]:
        """Generate completion using Ollama API"""

        # Convert messages to Ollama format
        prompt = self._messages_to_prompt(messages)

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "seed": seed,
                "stop": ["Human:", "Assistant:", "\n\nHuman:", "\n\nAssistant:", "\n\n\n"]
            }
        }

        try:
            response = requests.post(
                f"{self.host}/api/generate",
                json=payload,
                timeout=30
            )
            response.raise_for_status()

            result = response.json()
            return {
                "content": result.get("response", "").strip(),
                "model": self.model,
                "usage": {
                    "total_tokens": result.get("eval_count", 0)
                }
            }

        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Ollama API error: {e}")

    def _messages_to_prompt(self, messages: List[Dict[str, str]]) -> str:
        """Convert messages to a single prompt string"""
        prompt_parts = []

        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if role == "system":
                prompt_parts.append(f"System: {content}")
            elif role == "user":
                prompt_parts.append(f"Human: {content}")
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {content}")

        prompt_parts.append("Assistant:")
        return "\n\n".join(prompt_parts)