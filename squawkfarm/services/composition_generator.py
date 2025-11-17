from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Set, Tuple
import random

from squawkfarm.services.loop_engine import LoopEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _infer_bass_register(base_midi: int, root_midi: int) -> int:
    """
    Choose a good bass register given the animal's base midi and the global root.

    Tries to keep bass around root-12 (an octave below the key) or near
    the animal's original pitch but not too high.
    """
    candidates = [
        root_midi - 12,      # one octave below root
        root_midi,           # at root
        base_midi,           # detected pitch
        base_midi - 12,      # one octave below detected
    ]

    # Prefer notes not higher than root+2
    filtered = [c for c in candidates if c <= root_midi + 2]
    if not filtered:
        filtered = candidates

    # Choose candidate closest to original pitch
    return min(filtered, key=lambda c: abs(c - base_midi))


def _collect_existing_bass_slots(engine: LoopEngine, current_animal_id: str) -> Set[int]:
    """
    Collect a set of slot indices that are already occupied by other bass animals.

    Uses get_slot_ranges to consider the entire span (start_slot .. start_slot+num_slots).
    """
    occupied_slots: Set[int] = set()

    for aid in engine.bass_animals:
        if aid == current_animal_id:
            continue

        for start_slot, num_slots in engine.get_slot_ranges(aid):
            for s in range(start_slot, start_slot + num_slots):
                occupied_slots.add(s)

    return occupied_slots


def _generate_bass_slots_for_measure(
    measure_index: int,
    slots_per_measure: int,
    slots_per_beat: int,
    occupied_slots: Set[int],
) -> List[int]:
    """
    Decide at which slots (within this measure) to place bass hits.

    Returns a list of absolute slot indices (within the global grid).
    Attempts to avoid overlapping exactly where other bass animals already play.
    """
    measure_start = measure_index * slots_per_measure

    # Rhythmic templates in BEAT indices (0-based)
    beat_templates: List[List[float]] = [
        [0, 2],           # beats 1 & 3
        [0, 2.5],         # beat 1 & "and of 3"
        [0, 1.5, 3],      # 1, "and of 2", 4
        [0, 1, 2, 3],     # four-on-the-floor
    ]

    beats = random.choice(beat_templates)

    slots: List[int] = []
    for beat in beats:
        local_offset = int(round(beat * slots_per_beat))
        slot = measure_start + local_offset

        # Small chance to rest entirely
        if random.random() < 0.15:
            continue

        # If another bass already occupies this slot, try a tiny nudge
        if slot in occupied_slots:
            # Try nudging by 8th note forward or backward
            nudges = [slots_per_beat // 2, -slots_per_beat // 2]
            random.shuffle(nudges)
            for n in nudges:
                alt = slot + n
                if measure_start <= alt < measure_start + slots_per_measure and alt not in occupied_slots:
                    slot = alt
                    break
            # Otherwise keep it overlapped – occasional doubling can be OK

        slots.append(slot)

    return slots


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_random_baseline(
    engine: LoopEngine,
    animal_id: str,
) -> None:
    """
    Generate a random bassline pattern for a given animal and write it into the grid.

    - Clears all existing loop instances for this animal.
    - Chooses a bass register from the animal's detected midi and the global root.
    - For each measure, picks a rhythmic template and populates slots.
    - Tries to avoid stacking hits directly on top of other bass animals.

    Parameters
    ----------
    engine : LoopEngine
        Global loop engine instance.
    animal_id : str
        Animal to generate a baseline for. It should already exist in engine.loops
        and generally should have role "bass" (but this is not enforced here).
    """
    loop = engine.loops.get(animal_id)
    
    slots_per_measure = engine.get_slots_per_measure()
    slots_per_beat = engine.get_slots_per_beat()
    total_slots = engine.get_total_slots()
    num_measures = max(1, total_slots // slots_per_measure)

    # Determine bass register for this animal
    base_midi = loop.midi
    root_midi = engine.get_root()
    bass_root = _infer_bass_register(base_midi, root_midi)
    bass_fifth = bass_root + 7

    # Look at other bass animals to avoid heavy overlap
    occupied_slots = _collect_existing_bass_slots(engine, animal_id)

    # Clear this animal's existing pattern
    engine.clear_loops_from_grid(animal_id)

    # Generate events measure by measure
    for m in range(num_measures):
        # occasional full-measure rest for variation
        if random.random() < 0.15:
            continue

        measure_slots = _generate_bass_slots_for_measure(
            m,
            slots_per_measure,
            slots_per_beat,
            occupied_slots,
        )

        for slot in measure_slots:
            # Choose root or fifth with some variation
            use_fifth = random.random() < 0.4
            midi = bass_fifth if use_fifth else bass_root
            engine.add_loop_to_grid(animal_id, slot, midi)
