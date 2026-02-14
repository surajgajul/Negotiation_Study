"""
Parsing and validation utilities for negotiation offers
"""

import re
from typing import Optional


def extract_first_int(text: str) -> Optional[int]:
    """
    Extract the first integer from text that could be a price.
    Looks for numbers in reasonable price ranges (1-999).
    """
    if not text:
        return None

    # Remove dollar signs and commas first
    clean_text = text.replace('$', '').replace(',', '')

    # Find all integers in the text (1-3 digits for reasonable prices)
    pattern = r'\b(\d{1,3})\b'  # 1-3 digits, word boundary
    matches = re.findall(pattern, clean_text)

    for match in matches:
        num = int(match)
        # Filter out obviously non-price numbers
        if 1 <= num <= 999:  # Reasonable price range
            return num

    return None


def clamp_offer(offer: int, min_val: int, max_val: int) -> int:
    """Clamp offer to valid range"""
    return max(min_val, min(max_val, offer))


def detect_acceptance(prev_offer: Optional[int], current_offer: Optional[int]) -> bool:
    """
    Detect if current offer represents acceptance of previous offer.
    Acceptance occurs when consecutive offers match exactly.
    """
    if prev_offer is None or current_offer is None:
        return False

    return prev_offer == current_offer


def validate_offer_range(offer: int, role: str, buyer_range: tuple, supplier_range: tuple) -> bool:
    """Validate that offer is within allowed range for role"""
    if role == "buyer":
        return buyer_range[0] <= offer <= buyer_range[1]
    else:  # supplier
        return supplier_range[0] <= offer <= supplier_range[1]


def extract_offer_from_message(text: str, role: str, buyer_range: tuple, supplier_range: tuple) -> Optional[int]:
    """
    Extract and validate offer from message text.
    Returns None if no valid offer found.
    """
    offer = extract_first_int(text)
    if offer is None:
        return None

    # Get appropriate range
    range_min, range_max = buyer_range if role == "buyer" else supplier_range

    # Clamp to range
    clamped_offer = clamp_offer(offer, range_min, range_max)

    return clamped_offer