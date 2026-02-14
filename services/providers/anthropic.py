"""
Anthropic provider for cloud LLM inference
"""

from typing import Dict, Any, List
import anthropic


class AnthropicProvider:
    """Anthropic API provider"""

    def __init__(self, api_key: str, model: str):
        if not api_key:
            raise ValueError("Anthropic API key is required")

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def complete(
        self,
        *,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        seed: int
    ) -> Dict[str, Any]:
        """Generate completion using Anthropic API"""

        # Anthropic expects separate system message
        system_message = ""
        chat_messages = []

        for msg in messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            else:
                chat_messages.append(msg)

        try:
            response = self.client.messages.create(
                model=self.model,
                system=system_message,
                messages=chat_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stop_sequences=["Human:", "Assistant:"]
            )

            return {
                "content": response.content[0].text.strip(),
                "model": self.model,
                "usage": {
                    "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
                    "prompt_tokens": response.usage.input_tokens,
                    "completion_tokens": response.usage.output_tokens
                }
            }

        except Exception as e:
            raise RuntimeError(f"Anthropic API error: {e}")