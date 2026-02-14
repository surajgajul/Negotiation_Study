"""
AWS Bedrock provider for Claude models
"""

from typing import Dict, Any, List
import json
import os
import boto3


class BedrockProvider:
    """AWS Bedrock API provider for Claude models"""

    def __init__(self, model: str):
        """Initialize Bedrock client with AWS credentials from environment"""

        region = os.getenv("AWS_REGION")
        access_key = os.getenv("AWS_ACCESS_KEY_ID")
        secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")

        if not region:
            raise ValueError("AWS_REGION environment variable is required")
        if not access_key:
            raise ValueError("AWS_ACCESS_KEY_ID environment variable is required")
        if not secret_key:
            raise ValueError("AWS_SECRET_ACCESS_KEY environment variable is required")

        self.client = boto3.client(
            "bedrock-runtime",
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key
        )
        self.model = model

    def complete(
        self,
        *,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        seed: int
    ) -> Dict[str, Any]:
        """Generate completion using AWS Bedrock Claude API (converse method)"""

        # Separate system message
        system_message = ""
        chat_messages = []

        for msg in messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            else:
                chat_messages.append(msg)

        try:
            # Build system parameter
            system_param = []
            if system_message:
                system_param = [{"text": system_message}]

            # Build messages for converse API
            converse_messages = []
            for msg in chat_messages:
                converse_messages.append({
                    "role": msg["role"],
                    "content": [{"text": msg["content"]}]
                })

            # Call converse API
            response = self.client.converse(
                modelId=self.model,
                messages=converse_messages,
                system=system_param,
                inferenceConfig={
                    "temperature": temperature,
                    "maxTokens": max_tokens
                }
            )

            # Extract text from response
            content = ""
            for block in response.get("output", {}).get("message", {}).get("content", []):
                if "text" in block:
                    content += block["text"]

            # Extract token usage
            usage = response.get("usage", {})
            total_tokens = usage.get("inputTokens", 0) + usage.get("outputTokens", 0)

            return {
                "content": content.strip(),
                "model": self.model,
                "usage": {
                    "total_tokens": total_tokens,
                    "prompt_tokens": usage.get("inputTokens", 0),
                    "completion_tokens": usage.get("outputTokens", 0)
                }
            }

        except Exception as e:
            raise RuntimeError(f"Bedrock API error: {e}")