from typing import List, Set
from random import random, choice, shuffle

from squawkfarm.services.composition.utils import (
    build_scale,
    extend_scale_across_register,
    snap_to_scale,
)

# Chance that a measure is *intentionally* a full rest
PER_MEASURE_REST_PROB = 0.15

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _infer_bass_register_candidate(base_midi: int, root_midi: int) -> int:
    """
    Choose an initial candidate MIDI pitch for the bass "root" before we
    snap it into the scale and the bass register.
    """
    candidates = [
        root_midi - 12,  # one octave below root
        root_midi,       # at the root
        base_midi,       # detected pitch of the animal
        base_midi - 12,  # one octave below detected pitch
    ]

    # Prefer candidates not much higher than the root
    filtered = [c for c in candidates if c <= root_midi + 2]
    if not filtered:
        filtered = candidates

    # Choose the candidate closest to the animal's actual pitch
    return min(filtered, key=lambda c: abs(c - base_midi))


def _collect_existing_bass_slots(engine, current_animal_id: str) -> Set[int]:
    """
    Collect all grid slots currently used by OTHER bass animals.
    """
    occupied: Set[int] = set()

    for aid in engine.bass_animals:
        # Only look at other bass animals
        if aid == current_animal_id:
            continue

        loop = engine.loops.get(aid)
        if loop is None:
            continue

        # get_loop_instance_info returns (start_slot, num_slots, midi)
        for start_slot, num_slots, _ in loop.get_loop_instance_info(engine.frame_to_slot):
            for s in range(start_slot, start_slot + num_slots):
                occupied.add(s)

    return occupied


def _generate_bass_slots_for_measure(
    measure_index: int,
    slots_per_measure: int,
    slots_per_beat: int,
    occupied_slots: Set[int],
) -> List[int]:
    """
    Decide at which slots (within a single measure) to place bass hits.

    The basic idea:
      - Pick one of a few predefined rhythmic templates (in beat units).
      - Convert each beat position into a grid slot.
      - Occasionally skip hits (rests) for variation.
      - If a slot conflicts with another bass, nudge it slightly
        forwards/backwards when possible.
    """
    # Starting slot index of this measure
    measure_start = measure_index * slots_per_measure

    # Rhythmic templates in BEAT indices (0-based).
    # For 4/4, beats would be 0,1,2,3 representing 1–4.
    # TODO: make dynamic
    beat_templates: List[List[float]] = [
        [0, 2],           # beats 1 & 3
        [0, 2.5],         # beat 1 & "and of 3"
        [0, 1.5, 3],      # 1, "and of 2", 4
        [0, 1, 2, 3],     # four-on-the-floor
    ]

    # Choose one pattern for this measure
    beats = choice(beat_templates)

    slots: List[int] = []
    for beat in beats:
        # Convert beat index into an integer slot offset
        local_offset = int(round(beat * slots_per_beat))
        slot = measure_start + local_offset

        # Small chance to drop this hit entirely (rest)
        if random() < 0.15:
            continue

        # If another bass already occupies this slot, try a small nudge
        if slot in occupied_slots:
            # Nudges are +/- half a beat worth of slots (e.g. 8th-note shift)
            nudges = [slots_per_beat // 2, -slots_per_beat // 2]
            shuffle(nudges)
            for n in nudges:
                alt = slot + n
                # Stay within this measure and avoid already-occupied slots
                if measure_start <= alt < measure_start + slots_per_measure and alt not in occupied_slots:
                    slot = alt
                    break
            # If no valid nudge found, we keep the original slot and accept overlap

        slots.append(slot)

    return slots


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_random_baseline(engine, animal_id: str) -> None:
    """
    Generate a random bassline pattern for a given animal and write it into
    the global grid via the LoopEngine.
    
    This function:
    1. Determines what pitch to use (bass root and fifth, staying in key)
    2. Generates a rhythmic pattern measure-by-measure
    3. Avoids overlapping with other bass animals
    4. Places the notes on the grid at the chosen MIDI pitches
    """
    loop = engine.loops.get(animal_id)
    
    # Get grid timing info: how many slots per measure/beat, total slots, total measures
    slots_per_measure = engine.get_slots_per_measure()
    slots_per_beat = engine.get_slots_per_beat()
    total_slots = engine.get_total_slots()
    num_measures = max(1, total_slots // slots_per_measure)

    loop_length_slots = engine.get_num_slots(loop)

    # ============================================================================
    # STEP 1: Figure out what MIDI notes to use for this bassline
    # ============================================================================
    low, high = engine.get_animal_pitch_range(animal_id)

    # Global key info
    root_midi = engine.get_root()
    mode = engine.get_key_mode()

    # Build one-octave scale for the key, then tile it ONLY inside [low, high]
    # So the extended_scale contains *all and only* legal notes for this animal.
    base_scale = build_scale(root_midi, mode)
    extended_scale = extend_scale_across_register(base_scale, low, high)

    # Find a good starting candidate for our bass "root" note:
    # this considers the animal's natural pitch and the key's root.
    candidate = _infer_bass_register_candidate(loop.midi, root_midi)

    # Snap candidate into the extended_scale, which is already confined to [low, high].
    bass_root = snap_to_scale(extended_scale, candidate)

    # Fifth above the root (7 semitones). This might step outside the octave,
    # so we'll wrap it back into [low, high] afterward.
    bass_fifth = bass_root + 7

    # Strictly enforce staying inside this animal's one-octave band:
    while bass_fifth > high:
        bass_fifth -= 12
    while bass_fifth < low:
        bass_fifth += 12

    # ============================================================================
    # STEP 2: Track which slots are already occupied to avoid collisions
    # ============================================================================
    used_slots = _collect_existing_bass_slots(engine, animal_id)

    # Wipe out any previous pattern for this animal so we can generate fresh
    engine.clear_loops_from_grid(animal_id)

    # ============================================================================
    # STEP 3: Generate the bassline measure by measure
    # ============================================================================
    for m in range(num_measures):
        measure_start = m * slots_per_measure

        # 15% chance to intentionally skip this entire measure (rest for variation)
        if random() < PER_MEASURE_REST_PROB:
            continue

        # Generate a list of slot positions where we want to place bass hits in this measure
        # This uses rhythmic templates like [0, 2] for beats 1 & 3
        measure_slots = _generate_bass_slots_for_measure(
            measure_index=m,
            slots_per_measure=slots_per_measure,
            slots_per_beat=slots_per_beat,
            occupied_slots=used_slots,
        )

        # FALLBACK: If the rhythmic generator returned no slots (maybe all hits got dropped
        # or all conflicted with other bass), try to at least put one hit on beat 1
        if not measure_slots:
            # Check if we have room for the entire recording length starting at beat 1
            # (measure_start + 0, measure_start + 1, ..., measure_start + loop_length_slots - 1)
            span_ok = all(
                (measure_start + o) not in used_slots
                for o in range(loop_length_slots)
            )
            if span_ok:
                # Add beat 1 as a single hit
                measure_slots = [measure_start]
            # If even this doesn't fit, this measure will be silent

        # ============================================================================
        # STEP 4: Place the bass hits on the grid
        # ============================================================================
        for slot in measure_slots:
            # 40% chance to use the fifth, 60% chance to use the root
            # This creates variety: mostly root with occasional fifth movement
            use_fifth = random() < 0.4
            midi = bass_fifth if use_fifth else bass_root
            
            # Actually add this loop instance to the grid at the chosen slot and MIDI pitch
            engine.add_loop_to_grid(animal_id, slot, midi)

            # Mark ALL slots that this bass hit will occupy as "used"
            for s in range(slot, slot + loop_length_slots):
                used_slots.add(s)
    
    # ============================================================================
    # DEBUG: Print generated bassline pattern
    # ============================================================================
    print(f"\n=== Generated Bassline for {animal_id} ===")
    print(f"Bass Root: {bass_root} (MIDI), Bass Fifth: {bass_fifth} (MIDI)")
    print(f"Total Measures: {num_measures}, Slots per Measure: {slots_per_measure}")
    
    # Get the final pattern from the engine
    loop_instances = engine.get_loop_instance_info(animal_id)
    print(f"Generated {len(loop_instances)} loop instances:")
    for i, (start_slot, num_slots, midi) in enumerate(loop_instances, 1):
        end_slot = start_slot + num_slots - 1
        measure = start_slot // slots_per_measure + 1
        beat_in_measure = (start_slot % slots_per_measure) / slots_per_beat + 1
        note_type = "Fifth" if midi == bass_fifth else "Root"
        print(f"  {i}. Slot {start_slot}-{end_slot} (Measure {measure}, Beat {beat_in_measure:.1f}): MIDI {midi} ({note_type})")
    print("=" * 50 + "\n")
