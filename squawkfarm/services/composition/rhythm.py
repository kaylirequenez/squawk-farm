from collections import Counter
from squawkfarm.services.composition.beat_templates import (
    STRONG_SLOTS,
    ROLE_TEMPLATES,
)

def _pick_templates_for_key(role: str, slots_per_measure: int, loop_slots: int) -> list[list[int]]:
    """
    Returns a non-empty list of templates (each template is a list[int] of local slots).
    Falls back to [[0]] if no templates exist for this role/key.
    """
    template_table = ROLE_TEMPLATES.get(role)
    key = (slots_per_measure, loop_slots)
    if not key in template_table:
        # TODO: erase
        print(f"No templates for role={role}, slots_per_measure={slots_per_measure}, loop_slots={loop_slots}")
    templates = template_table.get(key)
    return templates

def expand_template(
    template_slots: list[int],
    slots_per_measure: int,
    total_measures: int,
    active_measures: list[int] | None = None,
) -> list[int]:
    """
    template_slots: local positions inside ONE measure (0..slots_per_measure-1)
    active_measures:
        None -> all measures [0..total_measures-1]
        [i, j, ...] -> only those measure indices
    """
    if active_measures is None:
        active_measures = list(range(total_measures))

    result: list[int] = []
    for measure in active_measures:
        if not (0 <= measure < total_measures):
            continue
        offset = measure * slots_per_measure
        for s in template_slots:
            result.append(offset + s)
    return sorted(result)


def _candidate_measure_sets(total_measures: int) -> list[list[int] | None]:
    """
    Returns a small set of measure-activation patterns to try.
    None = all measures, [m] = only that measure.
    """
    candidates: list[list[int] | None] = [None]  # all measures
    for m in range(total_measures):
        candidates.append([m])  # single-bar options
    return candidates


def _score_template_pair_global(
    existing_global: list[int],
    candidate_global: list[int],
    slots_per_measure: int,
    total_measures: int,
) -> int:
    setA = set(existing_global)
    setB = set(candidate_global)

    strong_local = STRONG_SLOTS.get(slots_per_measure)
    strong_global = {
        m * slots_per_measure + s
        for m in range(total_measures)
        for s in strong_local
    }

    overlap = setA & setB
    union = setA | setB

    score = 0

    # some shared hits on strong beats can be nice
    if overlap & strong_global:
        score += 3

    unique_hits = len(union)
    if 2 <= unique_hits <= 12:
        score += 2
    elif unique_hits > 20:
        score -= 2

    # reward refinement-like relations
    if setA.issubset(setB) or setB.issubset(setA):
        score += 3

    return score


def _score_global_density(
    candidate_global: list[int],
    all_role_globals: list[list[int]],
    slots_per_measure: int,
) -> int:
    counts = Counter()
    for pattern in all_role_globals:
        for s in pattern:
            counts[s] += 1

    score = 0
    for s in candidate_global:
        c = counts.get(s, 0)
        if c == 0:
            score += 3   # fills empty space
        elif c == 1:
            score += 1   # light layering
        elif c == 2:
            score -= 1   # getting busy
        else:
            score -= 3   # 3+ layers on same slot is too much

    if len(candidate_global) > slots_per_measure:
        score -= 2  # very dense line

    return score


def _score_candidate_global(
    candidate_global: list[int],
    same_role_globals: list[list[int]],
    all_role_globals: list[list[int]],
    slots_per_measure: int,
    total_measures: int,
) -> int:
    same_role_score = sum(
        _score_template_pair_global(base, candidate_global, slots_per_measure, total_measures)
        for base in same_role_globals
    )

    density_score = _score_global_density(
        candidate_global,
        all_role_globals,
        slots_per_measure
    )

    return same_role_score + density_score

def generate_slots(
    role: str,
    loop_slots: int,
    slots_per_measure: int,
    total_measures: int,
    same_role_globals: list[list[int]],
    all_role_globals: list[list[int]],
    min_score: int | None = None,
    num_candidates: int = 4,
) -> list[dict]:
    """
    Generate candidate rhythmic patterns for a new animal.

    Args:
        role:
            "bass", "harmony", or "melody".
        loop_slots:
            Duration in slots for this animal (2, 4, 8, 12, 16).
        slots_per_measure:
            e.g. 16 for 4/4 on a 16th grid.
        total_measures:
            1–4.
        same_role_globals:
            Global slots for existing animals of this role.
        all_role_globals:
            Global slots for all animals (all roles).
        min_score:
            If provided, prefer candidates with score >= min_score,
            but always return at least 2 options if possible.

    Returns:
        A list of candidate dicts, sorted best → worst. Each dict:
            {
                "pattern": list[int],          # global slots
                "score": int,
                "template_slots": list[int],   # local slots in one measure
                "active_measures": list[int] | None,  # which measures use it
            }
    """
    templates = _pick_templates_for_key(role, slots_per_measure, loop_slots)
    candidates: list[dict] = []

    # If there are no animals at all yet, we can’t really score;
    # treat everything as score=0 so you still get multiple options.
    do_scoring = bool(all_role_globals or same_role_globals)

    for template_slots in templates:
        for active_measures in _candidate_measure_sets(total_measures):
            pattern = expand_template(
                template_slots,
                slots_per_measure,
                total_measures,
                active_measures=active_measures,
            )

            if do_scoring:
                score = _score_candidate_global(
                    pattern,
                    same_role_globals,
                    all_role_globals,
                    slots_per_measure,
                    total_measures,
                )
            else:
                score = 0

            candidates.append({
                "pattern": pattern,
                "score": score,
                "template_slots": template_slots,
                "active_measures": active_measures,
            })

    # Sort best → worst
    candidates.sort(key=lambda c: c["score"], reverse=True)

    # Apply min_score filter if requested
    if min_score is not None:
        filtered = [c for c in candidates if c["score"] >= min_score]
    else:
        filtered = candidates

    # Ensure at least 2 options if possible
    MIN_OPTIONS = 2

    # If enough filtered options, return up to num_candidates
    if len(filtered) >= MIN_OPTIONS:
        return filtered[:num_candidates]

    # Not enough options passed the threshold: pad with top-scoring ones
    # from the full candidate list until we reach MIN_OPTIONS.
    padded = list(filtered)
    seen_ids = {id(c) for c in padded}

    for c in candidates:
        if id(c) in seen_ids:
            continue
        padded.append(c)
        seen_ids.add(id(c))
        if len(padded) >= MIN_OPTIONS:
            break

    # If there still aren't enough (e.g. only 1 total candidate), just return what we have, up to num_candidates.
    return padded[:num_candidates]
