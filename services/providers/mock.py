"""
Mock provider for testing without API keys
Generates deterministic responses based on role and offer
"""

from typing import Dict, Any, List
import random


class MockProvider:
    """Mock LLM provider for testing"""

    def __init__(self, model: str = "mock"):
        self.model = model
        self.call_count = 0
        self.responses = {
            "buyer": [
                "That's too high. How about $45?",
                "I need a better price. Can you do $40?",
                "Your offer is $80. I can only go to $50.",
                "Let's meet in the middle at $55.",
                "I'll accept $60.",
                "Can you do $48?",
                "I counter at $52.",
                "How about $42?",
            ],
            "supplier": [
                "My minimum is $100. How much can you pay?",
                "I can do $85 per unit.",
                "The best I can offer is $75.",
                "Let's settle at $70.",
                "I'll accept $65.",
                "I can go down to $80.",
                "How about $78?",
                "My lowest is $72.",
            ]
        }

    def complete(
        self,
        *,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        seed: int
    ) -> Dict[str, Any]:
        """Generate mock completion"""

        # Extract role from system message if available
        role = "supplier"  # default
        for msg in messages:
            if msg.get("role") == "system":
                if "buyer" in msg.get("content", "").lower():
                    role = "buyer"
                elif "supplier" in msg.get("content", "").lower():
                    role = "supplier"

        # Use seed + call_count for variety while staying deterministic
        self.call_count += 1
        random.seed(seed + self.call_count)

        # Pick a response based on seed
        responses = self.responses.get(role, self.responses["supplier"])
        idx = (seed + self.call_count) % len(responses)
        response_text = responses[idx]

        # Extract a number from the response
        import re
        numbers = re.findall(r'\$?(\d+)', response_text)
        numeric_offer = int(numbers[-1]) if numbers else None

        return {
            "content": response_text,
            "model": self.model,
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "total_tokens": 120
            }
        }
