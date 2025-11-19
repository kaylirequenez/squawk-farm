"""Shared utilities for composition generation."""

from typing import List, Tuple

from squawkfarm.services.loop_engine import LoopEngine

MODE_INTERVALS = {
    "major": [0, 2, 4, 5, 7, 9, 11, 12],
    "minor": [0, 2, 3, 5, 7, 8, 10, 12],
    # TODO: maybe extend later: dorian, mixolydian, etc.
}

def build_scale(root_midi: int, mode: str) -> List[int]:
    """
    Build a one-octave scale (root .. root+12) for the given mode.
    If the mode is unknown, default to major.
    """
    offsets = MODE_INTERVALS.get(mode)
    return [root_midi + o for o in offsets]


def extend_scale_across_register(scale: List[int], low: int, high: int) -> List[int]:
    """
    Tile a one-octave scale across octaves to cover [low, high] inclusive.
    """
    if not scale:
        return []

    result: List[int] = []
    
    # Calculate starting octave: shift down until we're below the low bound
    base_root = scale[0]
    start_octave = (low - base_root) // 12 - 1  # Start one octave below to catch all notes
    
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
    Get preferred (low, high) MIDI range for a role.
    """
    if role == "bass":
        return (36, 52)   # C2–E3-ish
    elif role == "harmony":
        return (48, 72)   # C3–C5
    elif role == "melody":
        return (60, 84)   # C4–C6

def make_role_scale_for_engine(engine: LoopEngine, role: str) -> List[int]:
    """
    Convenience: build an extended scale in the preferred register
    for a given role using the engine's current root & key_mode.
    """
    root = engine.get_root()
    mode = engine.get_key_mode()
    base_scale = build_scale(root, mode)
    low, high = get_role_register(role)
    return extend_scale_across_register(base_scale, low, high)