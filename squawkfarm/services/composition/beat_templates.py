STRONG_SLOTS = {
    16: {0, 8},             # 4/4: beats 1 & 3 -> slots 0, 8
}

# -------------------------------------------------------------------
# BASS TEMPLATES: keyed by (slots_per_measure, loop_slots)
# slots_per_measure = 16 for 4/4 on a 16th grid
# -------------------------------------------------------------------
BASS_TEMPLATES = {
    # 4/4, 0.5-beat loop -> loop_slots = 2
    (16, 2): [
        [0],                            # 0.0
        [2],                            # 0.5
        [0, 8],                         # 0.0, 2.0
        [2, 10],                        # 0.5, 2.5
        [0, 4, 8, 12],                  # 1, 2, 3, 4
        [2, 6, 10, 14],                 # off-beats
        [0, 2, 4, 6, 8, 10, 12, 14],    # straight 8ths / 16ths
        [0, 6, 8, 14],                  # syncopated
    ],

    # 4/4, 1-beat loop -> loop_slots = 4
    (16, 4): [
        [0, 8],                         # beats 1 & 3
        [0],                            # beat 1
        [8],                            # beat 3
        [0, 12],                        # beats 1 & 4
    ],

    # 4/4, 2-beat loop -> loop_slots = 8
    (16, 8): [
        [0],                            # phrase starting on beat 1
        [8],                            # phrase starting on beat 3
        [0, 8],                         # two half-bar phrases
    ],

    # 4/4, 3-beat loop -> loop_slots = 12
    (16, 12): [
        [0],                            # covers beats 1–3
        [4],                            # covers beats 2–4
    ],

    # 4/4, 4-beat loop -> loop_slots = 16
    (16, 16): [
        [0],                            # full bar from 1–4
    ],
}


HARMONY_TEMPLATES = {
    # 4/4, 0.5-beat loop -> loop_slots = 2
    (16, 2): [
        [0],                            # beat 1
        [2],                            # & of 1
        [0, 8],                         # beats 1 & 3
        [2, 10],                        # off-beats between 1–2 and 3–4
        [0, 4, 8, 12],                  # chord every beat
        [2, 6, 10, 14],                 # classic off-beat comping
        [0, 6, 8, 14],                  # syncopated mix
    ],

    # 4/4, 1-beat loop -> loop_slots = 4
    (16, 4): [
        [0],                            # chord on beat 1
        [0, 8],                         # chords on beats 1 & 3
        [0, 4, 8, 12],                  # chord every beat
    ],

    # 4/4, 2-beat loop -> loop_slots = 8
    (16, 8): [
        [0],                            # over beats 1–2
        [8],                            # over beats 3–4
        [0, 8],                         # two half-bar chords
    ],

    # 4/4, 3-beat loop -> loop_slots = 12
    (16, 12): [
        [0],                            # 1–3
        [4],                            # 2–4
    ],

    # 4/4, 4-beat loop -> loop_slots = 16
    (16, 16): [
        [0],                            # whole measure pad
    ],
}


MELODY_TEMPLATES = {
    # 4/4, 0.5-beat loop -> loop_slots = 2
    (16, 2): [
        [0],                            # pickup on beat 1
        [2],                            # upbeat (& of 1)
        [0, 2, 4],                      # 0.0, 0.5, 1.0
        [6, 8, 10],                     # 1.5, 2.0, 2.5
        [0, 2, 8, 10],                  # motif 1–1.5, answer 3–3.5
        [2, 4, 6, 10, 12],              # lightly syncopated
        [0, 4, 8, 12],                  # hits on every beat
        [0, 2, 4, 6, 8, 10, 12, 14],    # full bar of 8ths
        [0, 2, 6, 8, 12, 14],           # syncopated with spaces
    ],

    # 4/4, 1-beat loop -> loop_slots = 4
    (16, 4): [
        [0, 4, 8, 12],                  # hit every beat
        [0, 8],                         # 1 & 3
        [4, 12],                        # 2 & 4
    ],

    # 4/4, 2-beat loop -> loop_slots = 8
    (16, 8): [
        [0, 8],                         # two 2-beat phrases
        [0],                            # 1–2
        [8],                            # 3–4
    ],

    # 4/4, 3-beat loop -> loop_slots = 12
    (16, 12): [
        [0],                            # 1–3
        [4],                            # 2–4
        # you can add [0, 8] later with smarter logic
    ],

    # 4/4, 4-beat loop -> loop_slots = 16
    (16, 16): [
        [0],                            # one long phrase per measure
    ],
}


ROLE_TEMPLATES = {
    "bass": BASS_TEMPLATES,
    "harmony": HARMONY_TEMPLATES,
    "melody": MELODY_TEMPLATES,
}
