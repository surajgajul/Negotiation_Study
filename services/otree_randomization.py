"""
OTree-specific randomization service
Adapted from the backend randomization service for OTree models
"""

import secrets
import hashlib
from typing import Dict, List


class OTreeRandomization:
    """Handles randomization for OTree negotiation study"""

    def __init__(self):
        # 4 conditions: role (buyer/supplier) × initiator (human/ai)
        self.conditions = {
            1: ("buyer", "human"),     # Human buyer, human goes first
            2: ("buyer", "ai"),        # Human buyer, AI goes first
            3: ("supplier", "human"),  # Human supplier, human goes first
            4: ("supplier", "ai"),     # Human supplier, AI goes first
        }

    def get_round_config(
        self,
        round_num: int,
        sequence_id: int,
        block_order: str,
        session_seed: int
    ) -> Dict:
        """
        Get configuration for a specific round.

        Args:
            round_num: Round number (1-4)
            sequence_id: Condition ordering (1-4), controls counterbalancing
            block_order: Unused, kept for compatibility
            session_seed: Session seed for deterministic round seeds

        Returns:
            Dict with role, initiator, reflection_on, seed_round, etc.
        """
        round_index = round_num - 1

        # Get the counterbalanced condition sequence for this participant
        condition_sequence = self._get_condition_sequence(sequence_id)
        condition = condition_sequence[round_index]

        # Get condition details
        role_human, initiator = self.conditions[condition]

        # Generate deterministic round seed
        round_seed = self._generate_round_seed(session_seed, round_index)

        return {
            "round_num": round_num,
            "block_number": 1,
            "round_in_block": round_num,
            "player_role": role_human,
            "initiator": initiator,
            "reflection_on": False,
            "seed_round": round_seed,
        }

    def _get_condition_sequence(self, sequence_id: int) -> List[int]:
        """Get the 4-condition ordering for a given sequence ID (Latin square)"""
        sequences = {
            1: [1, 2, 3, 4],  # buyer-human, buyer-ai, supplier-human, supplier-ai
            2: [2, 1, 4, 3],  # buyer-ai, buyer-human, supplier-ai, supplier-human
            3: [3, 4, 1, 2],  # supplier-human, supplier-ai, buyer-human, buyer-ai
            4: [4, 3, 2, 1],  # supplier-ai, supplier-human, buyer-ai, buyer-human
        }
        return sequences[sequence_id]

    def _generate_round_seed(self, session_seed: int, round_index: int) -> int:
        """Generate deterministic seed for a specific round"""
        combined = f"{session_seed}_{round_index}"
        hash_obj = hashlib.sha256(combined.encode())
        return int(hash_obj.hexdigest()[:8], 16) & 0xFFFFFFFF

    @staticmethod
    def assign_participant(participant_token: str) -> Dict:
        """
        Assign participant to experimental condition.
        Uses participant token hash for deterministic assignment.
        """
        token_hash = hashlib.sha256(participant_token.encode()).hexdigest()
        hash_int = int(token_hash[:8], 16)

        # Assign sequence (1-4) for counterbalancing
        sequence_id = (hash_int % 4) + 1

        # Generate session seed
        session_seed = secrets.randbits(32)

        return {
            "block_order": "Off",  # Kept for compatibility, reflection always off
            "sequence_id": sequence_id,
            "session_seed": session_seed,
        }
