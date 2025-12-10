"""Models for chord progressions."""

from dataclasses import dataclass


@dataclass
class Chord:
    """
    A chord in the progression.

    degree: 1–7 scale degree (relative to global key)
    quality: e.g. "maj7", "min7", "dom7", "dim", etc.
    inversion: 0 = root position, 1 = first inversion, etc.
    """

    degree: int
    quality: str = "triad"
    inversion: int = 0


class ChordProgression:
    """
    Sequence of chords, one per measure (or pattern repeated).
    """

    def __init__(self, chords):
        if not chords:
            raise ValueError("ChordProgression requires at least one chord.")
        self.chords = chords

    def get_chord_at_measure(self, measure_index):
        """
        Return the chord for a given measure index.
        Loops if measure_index >= len(chords).
        """
        idx = measure_index % len(self.chords)
        return self.chords[idx]

    def __len__(self):
        return len(self.chords)

    def __getitem__(self, index):
        return self.chords[index]

    # TODO: Maxine - update however you see fit
    # maybe later we don't do it per measure ?
    @classmethod
    def generate_random_progression(cls, key_mode, num_measures):
        """
        Create a progression of length `num_measures`.
        """
        if key_mode == "minor":
            # i – VI – VII – v
            pattern = [
                Chord(degree=1, quality="min"),  # i
                Chord(degree=6, quality="maj"),  # VI
                Chord(degree=7, quality="maj"),  # VII
                Chord(degree=5, quality="min"),  # v
            ]
        else:
            # major: I – V – vi – IV
            pattern = [
                Chord(degree=1, quality="maj"),  # I
                Chord(degree=5, quality="maj"),  # V
                Chord(degree=6, quality="min"),  # vi
                Chord(degree=4, quality="maj"),  # IV
            ]

        if num_measures <= len(pattern):
            chords = pattern[:num_measures]
        else:
            chords = []
            i = 0
            while len(chords) < num_measures:
                chords.append(pattern[i % len(pattern)])
                i += 1

        return cls(chords)
