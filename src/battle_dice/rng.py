"""BD-PCG32-v1: the pinned, deterministic randomness service (BD-PRD-MVP-001 section 14.4).

Algorithm
---------
* PCG-XSH-RR 64/32 with 64-bit unsigned wraparound and multiplier 6364136223846793005.
* Standard two-draw PCG initialisation from ``(initial_state, stream_selector)``.
* Independent named streams (``dice``, ``enemy``, ``rewards``) are derived from the root seed by
  ``SHA-256("battle-dice-rng-v1|<decimal seed>|<stream name>")``: bytes 0..7 little-endian give the
  initial state, bytes 8..15 little-endian give the stream selector.
* Bounded integers use rejection sampling, so results carry no modulo bias.

Stream positions are plain integers held in :class:`~battle_dice.core.models.RngStreamState`, so
they are copied, rolled back and serialised together with the rest of the authoritative state.
No global random state is used anywhere in the rules engine.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

from battle_dice.core.models import RngStreamState

ALGORITHM = "BD-PCG32-v1"
STREAM_NAMES = ("dice", "enemy", "rewards")

_MASK64 = (1 << 64) - 1
_MASK32 = (1 << 32) - 1
_MULTIPLIER = 6364136223846793005
_DERIVATION_PREFIX = "battle-dice-rng-v1"


def _advance(state: int, increment: int) -> int:
    return (state * _MULTIPLIER + increment) & _MASK64


def _output(old_state: int) -> int:
    """XSH-RR output function applied to the state *before* it is advanced."""
    xorshifted = (((old_state >> 18) ^ old_state) >> 27) & _MASK32
    rot = old_state >> 59
    return ((xorshifted >> rot) | (xorshifted << ((-rot) & 31))) & _MASK32


def seed_stream(initial_state: int, stream_selector: int) -> RngStreamState:
    """Standard PCG32 seeding: zero state, odd increment, draw, add initial state, draw."""
    stream = RngStreamState(state=0, increment=((stream_selector << 1) | 1) & _MASK64, draws=0)
    stream.state = _advance(stream.state, stream.increment)
    stream.state = (stream.state + (initial_state & _MASK64)) & _MASK64
    stream.state = _advance(stream.state, stream.increment)
    return stream


def derive_stream(seed: int, stream_name: str) -> RngStreamState:
    """Derive one named stream from the unsigned 64-bit root seed."""
    validate_seed(seed)
    digest = hashlib.sha256(f"{_DERIVATION_PREFIX}|{seed}|{stream_name}".encode()).digest()
    initial_state = int.from_bytes(digest[0:8], "little")
    selector = int.from_bytes(digest[8:16], "little")
    return seed_stream(initial_state, selector)


def derive_streams(seed: int) -> dict[str, RngStreamState]:
    return {name: derive_stream(seed, name) for name in STREAM_NAMES}


def validate_seed(seed: int) -> None:
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= _MASK64:
        raise ValueError("seed must be an unsigned 64-bit integer")


def next_u32(stream: RngStreamState) -> int:
    """Draw one unsigned 32-bit value and advance the stream exactly once."""
    old = stream.state
    stream.state = _advance(old, stream.increment)
    stream.draws += 1
    return _output(old)


def bounded(stream: RngStreamState, n: int) -> int:
    """Uniform integer in ``[0, n)`` without modulo bias."""
    if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= (1 << 32):
        raise ValueError("n must be a positive integer no greater than 2**32")
    threshold = ((1 << 32) - n) % n
    while True:
        value = next_u32(stream)
        if value >= threshold:
            return value % n


def weighted_index(stream: RngStreamState, weights: Sequence[int]) -> int:
    """Choose an index by cumulative positive integer weights (callers supply stable-ID order)."""
    if any(isinstance(w, bool) or not isinstance(w, int) or w < 0 for w in weights):
        raise ValueError("weights must be non-negative integers")
    total = sum(weights)
    if total <= 0:
        raise ValueError("at least one weight must be positive")
    return index_for_roll(weights, bounded(stream, total))


def index_for_roll(weights: Sequence[int], roll: int) -> int:
    """Map a roll in ``[0, sum(weights))`` to an index by cumulative weights."""
    cumulative = 0
    for index, weight in enumerate(weights):
        cumulative += weight
        if roll < cumulative:
            return index
    raise ValueError("roll is outside the cumulative weight range")
