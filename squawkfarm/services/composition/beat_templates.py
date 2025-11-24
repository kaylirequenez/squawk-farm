"""
Beat templates and strong-beat definitions for each time signature.
"""
from typing import Dict, List, Tuple, Set

# ---------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------

Beat = float
BeatTemplate = List[Beat]
TemplateKey = Tuple[int, int]  # (beats_per_measure, loop_beats_int)
TemplateTable = Dict[TemplateKey, List[BeatTemplate]]

STRONG_BEATS: Dict[int, Set[int]] = {
    2: {0},        # 2/4: beat 1
    3: {0},        # 3/4: beat 1
    4: {0, 2},     # 4/4: beats 1 and 3
    6: {0, 3},     # 6/8 or 6/4: beats 1 and 4
    9: {0, 3, 6},  # 9/8 or 9/4: 1, 4, 7
    12: {0, 3, 6, 9},  # 12/8 or 12/4: 1, 4, 7, 10
}

# TODO: incorporate medium beats into rhythmic logic later
MEDIUM_BEATS: Dict[int, Set[int]] = {
    2: {1},
    3: {1, 2},
    4: {1, 3},
    6: {2, 5},
    9: {2, 5, 8},
    12: {2, 5, 8, 11},
}

BASS_TEMPLATES: TemplateTable = {
    # --------------------------------------------------------------
    # 4/4, 1-beat loop
    #   Typical use: short bass hit, 1 beat long.
    # --------------------------------------------------------------
    (4, 1): [
        [0.0, 2.0],      # strong 1 & 3 (classic two-hit bass)
        [0.0],           # just downbeat
        [2.0],           # just beat 3
        [0.0, 3.0],      # 1 & 4, a bit more driving
    ],

    # --------------------------------------------------------------
    # 4/4, 2-beat loop
    #   Typical use: 2-beat bass phrase.
    #   Each event spans 2 beats (1–2 or 3–4).
    # --------------------------------------------------------------
    (4, 2): [
        [0.0],           # 2-beat phrase starting on beat 1
        [2.0],           # 2-beat phrase starting on beat 3
        [0.0, 2.0],      # two half-bar phrases (engine may thin these)
    ],

    # --------------------------------------------------------------
    # 4/4, 3-beat loop
    #   Long bass phrase, almost full bar.
    #   Only one per measure usually makes sense.
    # --------------------------------------------------------------
    (4, 3): [
        [0.0],           # 3-beat phrase starting on beat 1 (covers 1–3)
        [1.0],           # 3-beat phrase starting on beat 2 (covers 2–4)
    ],

    # --------------------------------------------------------------
    # 4/4, 4-beat loop
    #   Full-bar bass phrase.
    #   Per-measure template is usually just one placement.
    # --------------------------------------------------------------
    (4, 4): [
        [0.0],           # full bar from beat 1 to beat 4
    ],
    # TODO: extend later
}

HARMONY_TEMPLATES: TemplateTable = {
    # 4/4, 1-beat harmony loop
    (4, 1): [
        [0.0],                         # chord on beat 1
        [0.0, 2.0],                    # chords on beats 1 & 3
        [0.0, 1.0, 2.0, 3.0],          # chord every beat (engine can thin)
    ],

    # 4/4, 2-beat harmony loop
    (4, 2): [
        [0.0],                         # chord over beats 1–2
        [2.0],                         # chord over beats 3–4
        [0.0, 2.0],                    # two half-bar chords
    ],

    # 4/4, 3-beat harmony loop
    (4, 3): [
        [0.0],                         # long chord from beat 1–3
        [1.0],                         # long chord from beat 2–4
    ],

    # 4/4, 4-beat harmony loop
    (4, 4): [
        [0.0],                         # whole-measure pad from 1–4
    ],
    # TODO: extend later
}

MELODY_TEMPLATES: TemplateTable = {
    # 4/4, 1-beat melody loop (short phrase)
    (4, 1): [
        [0.0, 1.0, 2.0, 3.0],          # hit every beat
        [0.0, 2.0],                    # call-and-response on 1 & 3
        [1.0, 3.0],                    # off-strong beats 2 & 4
    ],

    # 4/4, 2-beat melody loop
    (4, 2): [
        [0.0, 2.0],                    # two 2-beat phrases per bar (1–2, 3–4)
        [0.0],                         # 2-beat phrase starting on beat 1
        [2.0],                         # 2-beat phrase starting on beat 3
    ],

    # 4/4, 3-beat melody loop
    (4, 3): [
        [0.0],                         # 3-beat phrase from 1–3
        [1.0],                         # 3-beat phrase from 2–4
        # you can add [0.0, 2.0] later with smarter engine logic
    ],

    # 4/4, 4-beat melody loop (full-bar phrase)
    (4, 4): [
        [0.0],                         # one long phrase per measure
        # TODO: variants staggered across measures
    ],
    # TODO: extend later
}

ROLE_TEMPLATES: Dict[str, TemplateTable] = {
    "bass": BASS_TEMPLATES,
    "harmony": HARMONY_TEMPLATES,
    "melody": MELODY_TEMPLATES,
}
