from squawkfarm.services.composition.beat_templates import (
    STRONG_BEATS,
    ROLE_TEMPLATES,
)


def _quantize_loop_beats(loop_beats):
    return max(1, int(round(loop_beats)))


def _compute_global_beats_from_template(template_beats, loop_beats, beats_per_measure, total_measures):
    total_beats = beats_per_measure * total_measures
    starts = []

    prev_start = None

    for m in range(total_measures):
        base = m * beats_per_measure

        for beat_in_measure in template_beats:
            candidate = base + beat_in_measure

            if candidate + loop_beats > total_beats:
                continue

            if prev_start is not None:
                prev_end = prev_start + loop_beats
                if candidate < prev_end:
                    continue

            starts.append(candidate)
            prev_start = candidate

    return starts


def _generate_role_beats_for_first_animal(role, loop_beats, beats_per_measure, total_measures):
    loop_beats_int = _quantize_loop_beats(loop_beats)

    template_table = ROLE_TEMPLATES.get(role)
    key = (beats_per_measure, loop_beats_int)
    templates = template_table.get(key)
    template_beats = templates[0]

    return _compute_global_beats_from_template(template_beats, loop_beats, beats_per_measure, total_measures)


def _score_template_pair(base_template, candidate_template, beats_per_measure):
    setA = {int(b) for b in base_template}
    setB = {int(b) for b in candidate_template}

    strong_beats = STRONG_BEATS.get(beats_per_measure, {0})
    overlap = setA & setB
    union = setA | setB

    score = 0

    if overlap & strong_beats:
        score += 3

    unique_hits = len(union)
    if unique_hits in (2, 3):
        score += 2
    elif unique_hits > 3:
        score -= 2

    if setA.issubset(setB) or setB.issubset(setA):
        score += 3

    last_beat = beats_per_measure - 1
    if last_beat in setA and last_beat in setB:
        score -= 2

    return score


def _score_template_vs_many(candidate, existing_templates, beats_per_measure):
    return sum(
        _score_template_pair(base, candidate, beats_per_measure)
        for base in existing_templates
    )


def _generate_role_beats_for_layer(role, loop_beats, beats_per_measure, total_measures, existing_templates):
    loop_beats_int = _quantize_loop_beats(loop_beats)

    template_table = ROLE_TEMPLATES.get(role)
    key = (beats_per_measure, loop_beats_int)
    templates = template_table.get(key)

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
    
    
def generate_beats(role, loop_beats, beats_per_measure, total_measures, existing_templates):
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
    
