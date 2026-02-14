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
        # Block orders: reflection off/on vs on/off
        self.block_orders = ["OffOn", "OnOff"]

        # Within-block sequences (role × initiator combinations)
        self.sequences = list(range(1, 9))

        # Condition mapping
        self.conditions = {
            1: ("buyer", "human", False),    # Human buyer, human first, no reflection
            2: ("buyer", "ai", False),       # Human buyer, AI first, no reflection
            3: ("supplier", "human", False), # Human supplier, human first, no reflection
            4: ("supplier", "ai", False),    # Human supplier, AI first, no reflection
            5: ("buyer", "human", True),     # Human buyer, human first, with reflection
            6: ("buyer", "ai", True),        # Human buyer, AI first, with reflection
            7: ("supplier", "human", True),  # Human supplier, human first, with reflection
            8: ("supplier", "ai", True),     # Human supplier, AI first, with reflection
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
            round_num: Round number (1-8, not 0-indexed)
            sequence_id: Within-block sequence (1-8)
            block_order: "OffOn" or "OnOff" (unused, kept for compatibility)
            session_seed: Session seed for deterministic round seeds

        Returns:
            Dict with role, initiator, reflection_on, block_number, round_in_block
        """
        # Convert to 0-indexed
        round_index = round_num - 1

        # Determine which block we're in (0 or 1)
        block_id = round_index // 4

        # Round within block (0-3, will be 1-4 for display)
        round_in_block = (round_index % 4) + 1

        # Balanced random reflection: exactly 4 ON and 4 OFF, shuffled per participant
        import random
        rng = random.Random(session_seed)
        reflection_schedule = [True] * 4 + [False] * 4
        rng.shuffle(reflection_schedule)
        reflection_on = reflection_schedule[round_index]

        # Map sequence to conditions within the block
        condition_sequence = self._get_condition_sequence(sequence_id)
        base_condition = condition_sequence[round_index % 4]

        # Get condition details
        role_human, initiator, _ = self.conditions[base_condition]

        # Generate deterministic round seed
        round_seed = self._generate_round_seed(session_seed, round_index)

        return {
            "round_num": round_num,
            "block_number": block_id + 1,  # 1 or 2
            "round_in_block": round_in_block,  # 1-4
            "player_role": role_human,
            "initiator": initiator,
            "reflection_on": reflection_on,
            "seed_round": round_seed,
        }

    def _get_condition_sequence(self, sequence_id: int) -> List[int]:
        """Get the 4-condition sequence for a given sequence ID"""
        sequences = {
            1: [1, 2, 3, 4],  # buyer-human, buyer-ai, supplier-human, supplier-ai
            2: [2, 3, 4, 1],
            3: [3, 4, 1, 2],
            4: [4, 1, 2, 3],
            5: [1, 3, 2, 4],  # Different ordering
            6: [2, 4, 1, 3],
            7: [3, 1, 4, 2],
            8: [4, 2, 3, 1],
        }
        return sequences[sequence_id]

    def _find_condition(self, role: str, initiator: str, reflection: bool) -> int:
        """Find condition number for given parameters"""
        for cond_num, (r, i, refl) in self.conditions.items():
            if r == role and i == initiator and refl == reflection:
                return cond_num
        raise ValueError(f"No condition found for {role}, {initiator}, {reflection}")

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
        # Generate deterministic assignment from participant token
        token_hash = hashlib.sha256(participant_token.encode()).hexdigest()
        hash_int = int(token_hash[:8], 16)

        # Assign block order
        block_orders = ["OffOn", "OnOff"]
        block_order = block_orders[hash_int % len(block_orders)]

        # Assign sequence within block
        sequence_id = (hash_int // len(block_orders)) % 8 + 1

        # Generate session seed
        session_seed = secrets.randbits(32)

        return {
            "block_order": block_order,
            "sequence_id": sequence_id,
            "session_seed": session_seed,
        }
