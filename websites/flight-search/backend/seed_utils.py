"""Deterministic seeding utilities.

Same search parameters always produce the same flights and prices.
Uses SHA-256 hash of search params → integer seed for random.Random.
"""

import hashlib
import random


def make_seed(*parts: str | int | float) -> int:
    """Create a deterministic seed from arbitrary parts."""
    key = "|".join(str(p) for p in parts)
    h = hashlib.sha256(key.encode()).hexdigest()
    return int(h[:16], 16)


def seeded_random(*parts: str | int | float) -> random.Random:
    """Return a seeded Random instance for the given search params."""
    return random.Random(make_seed(*parts))
