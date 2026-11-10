"""BD-PCG32-v1 golden vectors and bounded-draw properties (section 14.4)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from battle_dice import RNG_ALGORITHM, RULES_VERSION, rng

GOLDEN = json.loads((Path(__file__).parent.parent / "golden" / "rng_vectors.json").read_text(encoding="utf-8"))


def test_golden_file_is_locked_to_this_rules_version():
    assert GOLDEN["algorithm"] == RNG_ALGORITHM == rng.ALGORITHM
    assert GOLDEN["rules_version"] == RULES_VERSION


def test_matches_published_pcg32_reference_output():
    # pcg32_srandom_r(&rng, 42u, 54u) from the PCG reference demo.
    stream = rng.seed_stream(42, 54)
    assert [rng.next_u32(stream) for _ in range(6)] == [
        0xA15C02B7, 0x7B47F409, 0xBA1D3330, 0x83D2F293, 0xBFA4784B, 0xCBED606E,
    ]
    assert stream.draws == 6


@pytest.mark.parametrize("seed", sorted(GOLDEN["seeds"]))
@pytest.mark.parametrize("name", rng.STREAM_NAMES)
def test_stream_golden_vectors(seed, name):
    expected = GOLDEN["seeds"][seed][name]
    stream = rng.derive_stream(int(seed), name)
    assert str(stream.state) == expected["seeded"]["state"]
    assert str(stream.increment) == expected["seeded"]["increment"]
    assert [rng.next_u32(stream) for _ in range(8)] == expected["u32"]
    for n in (4, 6, 8):
        fresh = rng.derive_stream(int(seed), name)
        assert [rng.bounded(fresh, n) for _ in range(12)] == expected[f"bounded_{n}"]


def test_stream_derivation_follows_the_documented_sha256_layout():
    seed = 20261109
    digest = hashlib.sha256(f"battle-dice-rng-v1|{seed}|dice".encode()).digest()
    expected = rng.seed_stream(int.from_bytes(digest[0:8], "little"), int.from_bytes(digest[8:16], "little"))
    derived = rng.derive_stream(seed, "dice")
    assert (derived.state, derived.increment) == (expected.state, expected.increment)
    assert derived.increment % 2 == 1


def test_streams_are_independent():
    streams = rng.derive_streams(7)
    assert set(streams) == set(rng.STREAM_NAMES)
    sequences = {name: tuple(rng.next_u32(s) for _ in range(8)) for name, s in streams.items()}
    assert len(set(sequences.values())) == len(rng.STREAM_NAMES)


def test_bounded_stays_in_range_and_covers_every_face():
    stream = rng.derive_stream(3, "dice")
    for n in (1, 4, 6, 8):
        values = [rng.bounded(stream, n) for _ in range(400)]
        assert min(values) >= 0 and max(values) < n
        assert set(values) == set(range(n))


def test_bounded_rejects_values_below_the_bias_threshold(monkeypatch):
    # For n = 3, threshold = (2**32 - 3) % 3 = 1, so a raw 0 must be redrawn (no modulo bias).
    n = 3
    assert ((1 << 32) - n) % n == 1
    scripted = iter([0, 0, 5])
    monkeypatch.setattr(rng, "next_u32", lambda stream: next(scripted))
    assert rng.bounded(rng.derive_stream(11, "dice"), n) == 5 % 3
    monkeypatch.undo()
    stream = rng.derive_stream(11, "dice")
    # Full-range and single-outcome edge cases.
    assert rng.bounded(stream, 1) == 0
    assert 0 <= rng.bounded(stream, 1 << 32) < (1 << 32)
    assert stream.draws == 2


@pytest.mark.parametrize("bad", [0, -1, (1 << 32) + 1, 2.0, True, "6"])
def test_bounded_rejects_invalid_n(bad):
    with pytest.raises(ValueError):
        rng.bounded(rng.derive_stream(1, "dice"), bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [-1, 1 << 64, 1.5, True, "7"])
def test_seed_must_be_unsigned_64_bit(bad):
    with pytest.raises(ValueError):
        rng.derive_stream(bad, "dice")  # type: ignore[arg-type]


def test_weighted_choice_uses_cumulative_weights_in_given_order():
    assert [rng.index_for_roll([1, 3], roll) for roll in range(4)] == [0, 1, 1, 1]
    assert [rng.index_for_roll([2, 0, 1], roll) for roll in range(3)] == [0, 0, 2]
    stream = rng.derive_stream(5, "enemy")
    picks = [rng.weighted_index(stream, [3, 0, 1]) for _ in range(200)]
    assert set(picks) == {0, 2}
    with pytest.raises(ValueError):
        rng.weighted_index(stream, [0, 0])
    with pytest.raises(ValueError):
        rng.weighted_index(stream, [1, -1])
    with pytest.raises(ValueError):
        rng.index_for_roll([1, 1], 2)


def test_same_seed_reproduces_the_same_sequence():
    first = rng.derive_stream(99, "rewards")
    second = rng.derive_stream(99, "rewards")
    assert [rng.bounded(first, 6) for _ in range(50)] == [rng.bounded(second, 6) for _ in range(50)]
