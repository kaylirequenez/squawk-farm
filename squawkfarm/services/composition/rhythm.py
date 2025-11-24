# squawkfarm/services/composition/rhythm.py
"""
Rhythm utilities and generators (beat-level only).

This module uses the beat templates from `beat_templates.py` to decide
WHEN an animal should sing in BEATS. 
"""

from typing import List

from squawkfarm.services.composition.beat_templates import (
    STRONG_BEATS,
    ROLE_TEMPLATES,
)


# ---------------------------------------------------------------------
# Helpers: loop length & beats
# ---------------------------------------------------------------------

# TODO: support ints later
def _quantize_loop_beats(loop_beats: float) -> int:
    if int(loop_beats) != loop_beats:
        print(loop_beats)
        print("ERROR")
    return max(1, int(round(loop_beats)))


def _compute_global_beats_from_template(
    template_beats: List[float],
    loop_beats: float,
    beats_per_measure: int,
    total_measures: int,
) -> List[float]:
    """
    Given beat positions *within a measure* (template_beats),
    tile them across measures to get global beat starts, enforcing:

      - no self-overlap: new start must not begin before the previous
        event ends (candidate >= prev_start + loop_beats)
      - no spill past the end of the full loop (total_measures * beats_per_measure)
    """
    total_beats = beats_per_measure * total_measures
    starts: List[float] = []

    prev_start: float | None = None

    for m in range(total_measures):
        base = m * beats_per_measure

        for beat_in_measure in template_beats:
            candidate = base + beat_in_measure

            # must fully fit inside the loop
            if candidate + loop_beats > total_beats:
                continue

            if prev_start is not None:
                prev_end = prev_start + loop_beats
                if candidate < prev_end:
                    print("ERROR: beat templates should prevent this")
                    continue

            starts.append(candidate)
            prev_start = candidate

    return starts


# ---------------------------------------------------------------------
# Generic: first-animal template selection per role (beats)
# ---------------------------------------------------------------------

def _generate_role_beats_for_first_animal(
    role: str,
    loop_beats: float,
    beats_per_measure: int,
    total_measures: int,
) -> List[float]:
    """
    Generate BEAT start positions for the FIRST animal of a given role.
    """
    loop_beats_int = _quantize_loop_beats(loop_beats)

    template_table = ROLE_TEMPLATES.get(role)
    key = (beats_per_measure, loop_beats_int)
    templates = template_table.get(key)
    template_beats = templates[0]

    return _compute_global_beats_from_template(template_beats, loop_beats, beats_per_measure, total_measures)


# ---------------------------------------------------------------------
# Bass-specific layering logic (beats)
# ---------------------------------------------------------------------

def _score_template_pair(
    base_template: List[float],
    candidate_template: List[float],
    beats_per_measure: int,
) -> int:
    """
    Heuristic scoring of how well two beat templates combine for bass.
    
    Heuristics:
      - bonus if they share at least one STRONG beat
      - bonus if total unique beats is small (2 or 3)
      - big bonus if one is a subset of the other (anchor vs fill)
      - penalty if both slam the last beat
    """
    setA = {int(b) for b in base_template}
    setB = {int(b) for b in candidate_template}

    strong_beats = STRONG_BEATS.get(beats_per_measure, {0})
    overlap = setA & setB
    union = setA | setB

    score = 0

    # 1) Shared strong beats
    if overlap & strong_beats:
        score += 3

    # 2) Total unique beats
    unique_hits = len(union)
    if unique_hits in (2, 3):
        score += 2
    elif unique_hits > 3:
        score -= 2

    # 3) Subset / nesting
    if setA.issubset(setB) or setB.issubset(setA):
        score += 3

    # 4) Both emphasizing the last beat
    last_beat = beats_per_measure - 1
    if last_beat in setA and last_beat in setB:
        score -= 2

    return score


def _score_template_vs_many(
    candidate: List[float],
    existing_templates: List[List[float]],
    beats_per_measure: int,
) -> int:
    """
    Score a candidate template against multiple existing templates
    by summing pairwise scores.
    """
    return sum(
        _score_template_pair(base, candidate, beats_per_measure)
        for base in existing_templates
    )


from squawkfarm.services.composition.beat_templates import (
    STRONG_BEATS,
    ROLE_TEMPLATES,
)

# ... existing helpers _quantize_loop_beats, _compute_global_beats_from_template,
#     _score_template_pair, _score_template_vs_many, etc. ...


def _generate_role_beats_for_layer(
    role: str,
    loop_beats: float,
    beats_per_measure: int,
    total_measures: int,
    existing_templates: List[List[float]],
) -> List[float]:
    """
    Generate BEAT start positions for an ADDITIONAL animal of a given role.

    Behavior:
      - Look up ROLE_TEMPLATES[role] for (beats_per_measure, loop_beats_int).
      - If no existing_templates, behave like "first animal" (just pick
        the first template).
      - If existing_templates are provided:
          * score each candidate template against all existing ones
          * choose the highest-scoring template
      - Tile across measures with no self-overlap.
    """
    loop_beats_int = _quantize_loop_beats(loop_beats)
    
    template_table = ROLE_TEMPLATES.get(role)
    key = (beats_per_measure, loop_beats_int)
    templates = template_table.get(key)
    
    # Score each candidate template against all existing ones
    scored_templates = [
        (t, _score_template_vs_many(t, existing_templates, beats_per_measure))
        for t in templates
    ]
    base_template_beats, _ = max(
        scored_templates,
        key=lambda pair: pair[1],
    )

    return _compute_global_beats_from_template(
        template_beats=base_template_beats,
        loop_beats=loop_beats,
        beats_per_measure=beats_per_measure,
        total_measures=total_measures,
    )
    
    
def generate_beats(
    role: str,
    loop_beats: float,
    beats_per_measure: int,
    total_measures: int,
    existing_templates: List[List[float]],
) -> List[float]:
    if not existing_templates:
        return _generate_role_beats_for_first_animal(
            role,
            loop_beats,
            beats_per_measure,
            total_measures,
        )
    
    return _generate_role_beats_for_layer(
        role,
        loop_beats,
        beats_per_measure,
        total_measures,
        existing_templates,
    )
    
