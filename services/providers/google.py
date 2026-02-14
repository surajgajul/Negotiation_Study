"""
Google provider for cloud LLM inference
"""

from typing import Dict, Any, List
import google.generativeai as genai


class GoogleProvider:
    """Google Generative AI provider"""

    def __init__(self, api_key: str, model: str):
        if not api_key:
            raise ValueError("Google API key is required")

        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model)

    def complete(
        self,
        *,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        seed: int
    ) -> Dict[str, Any]:
        """Generate completion using Google Generative AI"""

        # Convert messages to Google format
        prompt = self._messages_to_prompt(messages)

        try:
            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                    stop_sequences=["Human:", "Assistant:"]
                )
            )

            return {
                "content": response.text.strip(),
                "model": "gemini-pro",
                "usage": {
                    "total_tokens": response.usage_metadata.total_token_count if hasattr(response, 'usage_metadata') else 0
                }
            }

        except Exception as e:
            raise RuntimeError(f"Google API error: {e}")

    def _messages_to_prompt(self, messages: List[Dict[str, str]]) -> str:
        """Convert messages to a single prompt string"""
        prompt_parts = []

        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if role == "system":
                prompt_parts.append(f"System: {content}")
            elif role == "user":
                prompt_parts.append(f"User: {content}")
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {content}")

        return "\n\n".join(prompt_parts)