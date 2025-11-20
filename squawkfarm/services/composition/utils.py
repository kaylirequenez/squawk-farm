"""Shared utilities for composition generation."""

from typing import List, Tuple

MODE_INTERVALS = {
    "major": [0, 2, 4, 5, 7, 9, 11, 12],
    "minor": [0, 2, 3, 5, 7, 8, 10, 12],
    # TODO: maybe extend later: dorian, mixolydian, etc.
}

# TODO: change if we want
MIN_MIDI = 36   # C2
MAX_MIDI = 96   # C7


def build_scale(root_midi: int, mode: str) -> List[int]:
    """
    Build a one-octave scale (root .. root+12) for the given mode.
    If the mode is unknown, default to major.
    """
    offsets = MODE_INTERVALS.get(mode, MODE_INTERVALS["major"])
    return [root_midi + o for o in offsets]


def extend_scale_across_register(scale: List[int], low: int, high: int) -> List[int]:
    """
    Tile a one-octave scale across octaves to cover [low, high] inclusive.
    """
    if not scale:
        return []

    result: List[int] = []

    base_root = scale[0]
    # Start low enough so that after shifting we cover the 'low' bound
    start_octave = (low - base_root) // 12 - 1

    octave = start_octave
    while True:
        for note in scale:
            n = note + 12 * octave
            if n < low:
                continue
            if n > high:
                return result
            result.append(n)
        octave += 1


def snap_to_scale(extended_scale: List[int], midi: int) -> int:
    """Snap `midi` to the closest note in `extended_scale`."""
    if not extended_scale:
        return midi
    return min(extended_scale, key=lambda x: abs(x - midi))


def get_role_register(role: str) -> Tuple[int, int]:
    """
    Get a broad (low, high) MIDI range for a role.
    Used as a soft band; per-animal octaves will be carved inside this.
    """
    if role == "bass":
        return (36, 60)   # C2–C4-ish
    elif role == "harmony":
        return (48, 80)   # C3–G5-ish
    elif role == "melody":
        return (60, 96)   # C4–C7-ish
    return (MIN_MIDI, MAX_MIDI)


def get_animal_octave_range(
    base_midi: int,
    role: str,
    global_root: int,
) -> Tuple[int, int]:
    """
    Decide a SINGLE octave [low, high] for this animal:

      - Bottom is some global_root + 12*k (aligned with the key root),
      - We choose k so that base_midi falls inside or near that octave,
      - We clamp inside:
          - the role's broad range, and
          - the global MIN_MIDI..MAX_MIDI.

    Result always satisfies: high = low + 12.
    """
    # Broad role bounds (e.g. melody generally higher than bass)
    role_low, role_high = get_role_register(role)

    # Absolute safety clamp
    hard_low = max(MIN_MIDI, role_low)
    hard_high = min(MAX_MIDI, role_high)

    # Build candidate octave roots: global_root + 12*k within the hard bounds
    candidate_roots: List[int] = []
    k_min = -4
    k_max = 4
    for k in range(k_min, k_max + 1):
        root_k = global_root + 12 * k
        if root_k < hard_low or root_k + 12 > hard_high:
            continue
        candidate_roots.append(root_k)

    if not candidate_roots:
        # Fallback: just clamp one octave around global_root
        low = max(hard_low, min(global_root, hard_high - 12))
        high = low + 12
        return (low, high)

    # Prefer an octave where base_midi actually lies inside [root, root+12]
    inside = [
        r for r in candidate_roots
        if r <= base_midi <= r + 12
    ]
    if inside:
        octave_root = inside[0]
    else:
        # Otherwise choose the octave whose center is closest to the base pitch
        def center(r: int) -> float:
            return r + 6  # middle of the octave
        octave_root = min(candidate_roots, key=lambda r: abs(center(r) - base_midi))

    low = octave_root
    high = octave_root + 12

    # Extra safety clamp (should already be ok)
    low = max(low, hard_low)
    high = min(high, hard_high)

    # Ensure exactly one octave
    if high - low != 12:
        high = low + 12
        if high > hard_high:
            high = hard_high
            low = high - 12

    return (low, high)
