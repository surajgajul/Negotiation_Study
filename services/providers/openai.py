"""
OpenAI provider for cloud LLM inference
"""

from typing import Dict, Any, List
import openai


class OpenAIProvider:
    """OpenAI API provider"""

    def __init__(self, api_key: str, model: str, azure_endpoint: str = None, api_version: str = None):
        if not api_key:
            raise ValueError("API key is required")

        self.model = model
        self.is_azure = azure_endpoint is not None

        if self.is_azure:
            from openai import AzureOpenAI
            self.client = AzureOpenAI(
                api_key=api_key,
                api_version=api_version,
                azure_endpoint=azure_endpoint
            )
        else:
            from openai import OpenAI
            self.client = OpenAI(api_key=api_key)

    def complete(
        self,
        *,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        seed: int
    ) -> Dict[str, Any]:
        """Generate completion using OpenAI API"""

        try:
            kwargs = {
                "messages": messages
                # "temperature": temperature
                # "max_tokens": max_tokens
            }
            
            if not self.is_azure:
                # Only standard OpenAI supports these parameters
                kwargs["seed"] = seed
                kwargs["stop"] = ["Human:", "Assistant:"]
            
            response = self.client.chat.completions.create(
                model=self.model,
                **kwargs
            )

            return {
                "content": response.choices[0].message.content.strip(),
                "model": self.model,
                "usage": {
                    "total_tokens": response.usage.total_tokens,
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens
                }
            }

        except Exception as e:
            raise RuntimeError(f"OpenAI API error: {e}")