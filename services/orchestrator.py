"""
LLM Provider Orchestrator
Manages different AI providers (Ollama, OpenAI, Anthropic, Google) with a unified interface.
"""

import os
import yaml
import hashlib
from typing import Dict, Any, Optional, Protocol, List
from pathlib import Path

from .providers.ollama import OllamaProvider
from .providers.openai import OpenAIProvider
from .providers.anthropic import AnthropicProvider
from .providers.google import GoogleProvider
from .providers.mock import MockProvider
from .audit_log import AuditLogger


class LLMProvider(Protocol):
    """Protocol for LLM providers"""

    def complete(
        self,
        *,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        seed: int
    ) -> Dict[str, Any]:
        """Generate completion from messages"""
        ...


class Orchestrator:
    """Provider-agnostic LLM orchestrator"""

    def __init__(self, config_path: str = None):
        # Try multiple possible paths for config file
        if config_path is None:
            possible_paths = [
                "settings_study.yaml",
                "../settings_study.yaml",
                "config/study.yaml",
                "../config/study.yaml",
            ]
        else:
            possible_paths = [config_path]

        config = None
        for path in possible_paths:
            try:
                with open(path, 'r') as f:
                    config = yaml.safe_load(f)
                    break
            except FileNotFoundError:
                continue

        if config is None:
            raise FileNotFoundError(f"Could not find config file in any of these locations: {possible_paths}")

        self.config = config
        self.study_config = self.config.get('study', self.config)  # Support both nested and flat configs
        self.provider = self._load_provider()

    def _load_provider(self) -> LLMProvider:
        """Load the configured LLM provider with error checking"""
        from .providers.bedrock import BedrockProvider

        provider_name = self.study_config['model_provider']

        try:
            if provider_name == "mock":
                print("WARNING: Using mock LLM provider (for testing only)")
                return MockProvider(model=self.study_config.get('model_name', 'mock'))
            elif provider_name == "ollama":
                return OllamaProvider(
                    host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
                    model=self.study_config['model_name']
                )
            elif provider_name == "openai":
                # Check if using Azure OpenAI
                azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
                azure_api_version = os.getenv("AZURE_OPENAI_API_VERSION")
                api_key = os.getenv("OPENAI_API_KEY")

                if not api_key:
                    raise ValueError("OPENAI_API_KEY environment variable is not set. Please set it before running the app.")

                return OpenAIProvider(
                    api_key=api_key,
                    model=self.study_config.get('model_name', 'gpt-3.5-turbo'),
                    azure_endpoint=azure_endpoint,
                    api_version=azure_api_version
                )
            elif provider_name == "anthropic":
                api_key = os.getenv("ANTHROPIC_API_KEY")
                if not api_key:
                    raise ValueError("ANTHROPIC_API_KEY environment variable is not set.")

                return AnthropicProvider(
                    api_key=api_key,
                    model=self.study_config.get('model_name', 'claude-3-sonnet-20240229')
                )
            elif provider_name == "bedrock":
                return BedrockProvider(
                    model=self.study_config.get('model_name', 'anthropic.claude-3-5-sonnet-20241022-v2:0')
                )
            elif provider_name == "google":
                api_key = os.getenv("GOOGLE_API_KEY")
                if not api_key:
                    raise ValueError("GOOGLE_API_KEY environment variable is not set.")

                return GoogleProvider(
                    api_key=api_key,
                    model=self.study_config.get('model_name', 'gemini-pro')
                )
            else:
                raise ValueError(f"Unknown provider: {provider_name}")
        except Exception as e:
            print(f"ERROR: Failed to initialize LLM provider '{provider_name}': {str(e)}")
            raise

    def respond(
        self,
        *,
        role: str,
        reflection: bool,
        conversation_history: List[str],
        last_offer: Optional[int] = None,
        seed: int,
        bounds: tuple[int, int],
        session_code: str = "",
        round_number: int = 0,
        participant_code: str = "",
    ) -> Dict[str, Any]:
        """
        Generate AI response for negotiation

        Returns:
            {
                "text": str,
                "numeric_offer": int|None,
                "reflection_note": str|None
            }
        """
        audit_ctx = dict(session_code=session_code, round_number=round_number, participant_code=participant_code)

        reflection_note = None

        # Step 1: Reflection planning (if enabled)
        if reflection:
            planning_messages = self._build_planning_messages(
                role, conversation_history, last_offer, bounds
            )

            AuditLogger.log(
                event_type="llm_request",
                **audit_ctx,
                payload={
                    "step": "reflection",
                    "role": role,
                    "messages": planning_messages,
                    "temperature": self.study_config['temperature'],
                    "max_tokens": self.study_config['reflection_tokens'],
                    "seed": seed,
                },
            )

            plan_result = self.provider.complete(
                messages=planning_messages,
                temperature=self.study_config['temperature'],
                max_tokens=self.study_config['reflection_tokens'],
                seed=seed
            )

            reflection_note = plan_result.get('content', '')

            AuditLogger.log(
                event_type="llm_response",
                **audit_ctx,
                payload={
                    "step": "reflection",
                    "raw_content": reflection_note,
                    "model": plan_result.get('model', ''),
                    "usage": plan_result.get('usage', {}),
                },
            )

        # Step 2: Generate visible response
        response_messages = self._build_response_messages(
            role, conversation_history, last_offer, bounds, reflection_note
        )

        response_seed = seed + 1 if reflection else seed

        AuditLogger.log(
            event_type="llm_request",
            **audit_ctx,
            payload={
                "step": "response",
                "role": role,
                "reflection_enabled": reflection,
                "messages": response_messages,
                "temperature": self.study_config['temperature'],
                "max_tokens": 256,
                "seed": response_seed,
                "has_reflection_note": reflection_note is not None,
            },
        )

        result = self.provider.complete(
            messages=response_messages,
            temperature=self.study_config['temperature'],
            max_tokens=256,
            seed=response_seed
        )

        # Extract numeric offer from response
        from .parsing import extract_first_int, clamp_offer
        import re
        text = result.get('content', '')
        raw_offer = extract_first_int(text)
        numeric_offer = raw_offer
        if numeric_offer:
            clamped = clamp_offer(numeric_offer, bounds[0], bounds[1])
            if clamped != numeric_offer:
                # Replace the original number in text so text and offer match
                text = re.sub(
                    r'\$?\b' + str(numeric_offer) + r'\b',
                    f'${clamped}',
                    text,
                    count=1
                )
            numeric_offer = clamped

        AuditLogger.log(
            event_type="llm_response",
            **audit_ctx,
            payload={
                "step": "response",
                "raw_content": result.get('content', ''),
                "final_text": text,
                "model": result.get('model', ''),
                "usage": result.get('usage', {}),
                "extracted_offer_raw": raw_offer,
                "offer_after_clamp": numeric_offer,
                "was_clamped": raw_offer != numeric_offer if numeric_offer else False,
                "bounds": list(bounds),
            },
        )

        # If no numeric offer found and this is not a reflection step, try once more with clearer prompt
        if numeric_offer is None and not reflection:
            # Retry with more explicit instruction
            retry_messages = response_messages.copy()
            retry_messages[-1]["content"] += f"\n\nIMPORTANT: Your response MUST include a specific dollar amount between ${bounds[0]} and ${bounds[1]}. Example: 'I offer $55' or 'How about $45?'"

            AuditLogger.log(
                event_type="llm_request",
                **audit_ctx,
                payload={
                    "step": "retry",
                    "reason": "no_numeric_offer_in_first_response",
                    "seed": seed + 2,
                },
            )

            retry_result = self.provider.complete(
                messages=retry_messages,
                temperature=self.study_config['temperature'],
                max_tokens=256,
                seed=seed + 2  # Different seed for retry
            )

            retry_text = retry_result.get('content', '')
            retry_offer = extract_first_int(retry_text)
            if retry_offer:
                clamped = clamp_offer(retry_offer, bounds[0], bounds[1])
                if clamped != retry_offer:
                    retry_text = re.sub(
                        r'\$?\b' + str(retry_offer) + r'\b',
                        f'${clamped}',
                        retry_text,
                        count=1
                    )
                text = retry_text
                numeric_offer = clamped

            AuditLogger.log(
                event_type="llm_response",
                **audit_ctx,
                payload={
                    "step": "retry",
                    "raw_content": retry_result.get('content', ''),
                    "final_text": text,
                    "model": retry_result.get('model', ''),
                    "usage": retry_result.get('usage', {}),
                    "extracted_offer_raw": retry_offer,
                    "offer_after_clamp": numeric_offer,
                    "was_clamped": retry_offer != numeric_offer if numeric_offer else False,
                },
            )

        return {
            "content": text,
            "numeric_offer": numeric_offer,
            "reflection_note": reflection_note if self.config['logging']['keep_messages'] else None
        }

    def _build_planning_messages(
        self,
        role: str,
        conversation_history: List[str],
        last_offer: Optional[int],
        bounds: tuple[int, int]
    ) -> List[Dict[str, str]]:
        """Build messages for reflection planning using structured format from previous studies"""
        from .parsing import extract_first_int

        # Count current round
        round_number = len(conversation_history) // 2 + 1

        # Get partner role and last offers
        partner_role = "buyer" if role == "supplier" else "supplier"
        partner_last_offer = last_offer

        # Extract my last offer by scanning conversation history for my messages
        my_last_offer = None
        ai_prefix = "ai: "
        for msg in reversed(conversation_history):
            if msg.startswith(ai_prefix):
                my_last_offer = extract_first_int(msg)
                if my_last_offer is not None:
                    break

        if role == "buyer":
            system_prompt = f"""<think>
Current negotiation status:
- Last supplier offer: ${partner_last_offer if partner_last_offer else 'None'}
- My last offer: ${my_last_offer if my_last_offer else 'None'}
- Round: {round_number}/10

Quick analysis:
- Their offer suggests cost around: ${partner_last_offer - 20 if partner_last_offer else 'unknown'}
- My target profit margin: ~$30-40 per unit
- Should I: counter/accept/push harder?

Strategy: {'counter lower' if partner_last_offer and partner_last_offer > 65 else 'consider accepting' if partner_last_offer and partner_last_offer <= 50 else 'start aggressive'}
If the supplier offer has $1 or $2 difference with my last offer, consider accepting to save rounds and increase chances of deal.
</think>

You are analyzing the negotiation from the buyer perspective. Provide strategic thinking in this exact format above."""
        else:  # supplier
            system_prompt = f"""<think>
Current negotiation status:
- Last buyer offer: ${partner_last_offer if partner_last_offer else 'None'}
- My last offer: ${my_last_offer if my_last_offer else 'None'}
- Round: {round_number}/10

Quick analysis:
- Their offer gives me profit of: ${partner_last_offer - 30 if partner_last_offer else 'unknown'}
- Market seems to value around: ${partner_last_offer + 15 if partner_last_offer else 'unknown'}
- Should I: counter/accept/hold firm?

Strategy: {'counter higher' if partner_last_offer and partner_last_offer < 55 else 'consider accepting' if partner_last_offer and partner_last_offer >= 70 else 'start high'}
If the buyer offer has $1 or $2 difference with my last offer, consider accepting to save rounds and increase chances of deal.
</think>

You are analyzing the negotiation from the supplier perspective. Provide strategic thinking in this exact format above."""

        user_content = f"Current situation: {' | '.join(conversation_history[-4:]) if conversation_history else 'Starting negotiation'}"

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

    def _build_response_messages(
        self,
        role: str,
        conversation_history: List[str],
        last_offer: Optional[int],
        bounds: tuple[int, int],
        plan: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """Build messages for the visible response using proven prompts from previous studies"""

        # Use the proven prompts from previous AI-AI studies
        if role == "buyer":
            system_prompt = """You are a retailer negotiating wholesale price with a supplier. You want the LOWEST possible price.

YOUR PRIVATE INFO (do not reveal):
- You sell at: $100 per unit
- Demand: Normal distribution, mean 40 units, std 10
- Your profit = (100 - wholesale_price) × units_sold

RULES:
- Give SHORT responses only
- Make offers like "I offer $45" or "How about $38?"
- Accept good offers by saying "I accept $X"
- NO explanations, stories, or reasoning
- Price range: $1-99 only
- If the supplier offer has $1 or $2 difference with my last offer, consider accepting to save rounds and increase chances of deal.


Your response (keep it under 15 words):"""
        else:  # supplier
            system_prompt = """You are a supplier negotiating wholesale price with a retailer. You want the HIGHEST possible price above your costs.

YOUR PRIVATE INFO (do not reveal):
- Production cost: $30 per unit
- Your profit = (wholesale_price - 30) × units_sold

RULES:
- Give SHORT responses only
- Make offers like "I want $65" or "How about $58?"
- Accept good offers by saying "I accept $X"
- NO explanations, stories, or reasoning
- Price range: $31-200 only
- If the buyer offer has $1 or $2 difference with my last offer, consider accepting to save rounds and increase chances of deal.


Your response (keep it under 15 words):"""

        # Build user message
        user_content = ""
        if plan:
            user_content += f"Using this plan: {plan}\n\n"

        if last_offer:
            user_content += f"The other party offered: ${last_offer}\n"

        if conversation_history:
            user_content += f"Recent conversation: {' | '.join(conversation_history[-4:])}\n"

        user_content += (
            f"Produce a single-sentence message that includes one integer price "
            f"within your allowed range ${bounds[0]}-${bounds[1]}, or accept if the "
            f"counterpart price meets your target."
        )

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]