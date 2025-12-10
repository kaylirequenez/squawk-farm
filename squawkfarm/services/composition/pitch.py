import random
from typing import Dict, List, Tuple

PENTATONIC_INTERVALS = [0, 2, 4, 7, 9]

NUM_ROWS_PER_KEY = 8
POOL_LOW_MIDI = 36
POOL_HIGH_MIDI = 96


def build_pentatonic_pool(
    root_midi: int, low: int = POOL_LOW_MIDI, high: int = POOL_HIGH_MIDI
) -> List[int]:
    """
    Build a pentatonic pool of MIDI notes around the given root,
    clamped into [low, high].
    """
    notes: List[int] = []

    for octave_offset in range(-2, 4):
        base = root_midi + 12 * octave_offset
        for interval in PENTATONIC_INTERVALS:
            note = base + interval
            if low <= note <= high:
                notes.append(note)

    notes = sorted(set(notes))
    return notes


def generate_constrained_pentatonic_pitch_map(
    base_midi: int,
    root_midi: int,
    start_slots: List[int],
) -> Tuple[Dict[int, int], int]:
    pool = build_pentatonic_pool(root_midi)

    if not pool:
        pitch_map = {s: base_midi for s in start_slots}
        return pitch_map, base_midi

    # Initial max window size
    window_size = min(NUM_ROWS_PER_KEY, len(pool))

    # Find closest note in pool to base_midi
    closest_note = min(pool, key=lambda n: abs(n - base_midi))
    closest_idx = pool.index(closest_note)

    # Try to center around closest_idx but shrink the window
    # until it fits within one octave (<= 12 semitones span).
    while window_size > 1:
        min_bottom_idx = 0
        max_bottom_idx = len(pool) - window_size

        ideal_bottom_idx = closest_idx - window_size // 2
        bottom_idx = max(min_bottom_idx, min(max_bottom_idx, ideal_bottom_idx))

        span = pool[bottom_idx + window_size - 1] - pool[bottom_idx]
        if span <= 12:
            break  # good: this window fits in one octave
        window_size -= 1

    # Recompute bottom_idx with the final window_size
    min_bottom_idx = 0
    max_bottom_idx = len(pool) - window_size
    ideal_bottom_idx = closest_idx - window_size // 2
    bottom_idx = max(min_bottom_idx, min(max_bottom_idx, ideal_bottom_idx))

    window_min_idx = bottom_idx
    window_max_idx = bottom_idx + window_size - 1

    base_midi_for_ui = pool[bottom_idx]  # bottom row midi

    # Start random walk from closest_idx, clamped to window
    current_idx = max(window_min_idx, min(window_max_idx, closest_idx))

    pitch_map: Dict[int, int] = {}
    for s in start_slots:
        note = pool[current_idx]
        pitch_map[s] = note

        step = random.choice([-1, 0, 1, 1])
        current_idx = max(window_min_idx, min(window_max_idx, current_idx + step))

    return pitch_map, base_midi_for_ui
