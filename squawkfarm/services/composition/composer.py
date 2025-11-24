"""Composer class for managing musical context and roles."""
from typing import Dict, Set

from squawkfarm.models.progression import ChordProgression

MIN_ROOT = 48   # C3
MAX_ROOT = 72   # C5


class Composer:
    """
    Musical context and role logic.

    Keeps track of:
      - key_mode ('major' or 'minor')
      - root (MIDI note, global tonic)
      - chord_progression
      - counts of animals in each role
    """

    def __init__(self, key_mode: str, root: int, chord_progression: ChordProgression):
        self.key_mode = key_mode
        self.root = max(MIN_ROOT, min(MAX_ROOT, root))
        self.chord_progression = chord_progression

        self.animals_by_role: Dict[str, Set[str]] = {
            "bass": set(),
            "melody": set(),
            "harmony": set(),
            "percussion": set(),
        }

    # ------------------------------------------------------------------ #
    # internal helpers
    # ------------------------------------------------------------------ #
    
    def _choose_initial_root(self, base_midi: int) -> int:
        """
        Choose global root as the nearest C to base_midi, clamped to [C3, C5].
        """
        c_down = base_midi - (base_midi % 12)
        c_up = c_down + 12

        if abs(base_midi - c_down) <= abs(base_midi - c_up):
            nearest_c = c_down
        else:
            nearest_c = c_up
            
        print("Initial root chosen:", nearest_c)

        return max(MIN_ROOT, min(MAX_ROOT, nearest_c))

    def _guess_role_from_pitch(self, animal_midi: int, root_midi: int) -> str:
        """
        Basic pitch-based role guess:

          - bass: more than a fourth below root
          - melody: a fifth or more above root
          - otherwise: harmony
        """
        offset = animal_midi - root_midi  # in semitones

        if offset <= -5:
            return "bass"
        elif offset >= 7:
            return "melody"
        else:
            return "harmony"

    # ------------------------------------------------------------------ #
    # public API
    # ------------------------------------------------------------------ #

    def set_key_mode(self, key_mode: str) -> None:
        self.key_mode = key_mode

    def set_root(self, root: int) -> None:
        self.root = max(MIN_ROOT, min(MAX_ROOT, root))

    def set_chord_progression(self, progression: ChordProgression) -> None:
        self.chord_progression = progression

    def register_animal_role(self, animal_id: str, role: str) -> None:
        self.animals_by_role[role].add(animal_id)

    def unregister_animal_role(self, animal_id: str, role: str) -> None:
        self.animals_by_role[role].discard(animal_id)

    def change_animal_role(self, animal_id: str, old_role: str, new_role: str) -> None:
        if old_role == new_role:
            return
        self.unregister_animal_role(animal_id, old_role)
        self.register_animal_role(animal_id, new_role)

    def guess_initial_role(self, animal_midi: int, beats: int) -> str:
        """
        Guess an initial role using pitch + loop length + current role counts.
        This is the old guess_initial_role logic, just moved here.
        """
        base_role = self._guess_role_from_pitch(animal_midi, self.root)

        bass_count   = len(self.animals_by_role.get("bass"))
        melody_count = len(self.animals_by_role.get("melody"))
        offset = animal_midi - self.root

        # Keep at least one bass/melody if pitch suggests it
        if bass_count == 0 and base_role == "bass":
            return "bass"
        if melody_count == 0 and base_role == "melody":
            return "melody"

        # If bass is over-represented, push borderline lows toward harmony
        if base_role == "bass" and bass_count >= 2 and -7 <= offset:
            return "harmony"

        # If melody is over-represented, push borderline highs toward harmony
        if base_role == "melody" and melody_count >= 3 and offset <= 10:
            return "harmony"

        # TODO: percussion later
        print("Initial role guessed:", base_role)

        return base_role
    
    def handle_first_animal_if_needed(self, base_midi: int) -> None:
        """
        If this is the very first animal, adjust global root based on its pitch.
        """
        if all(len(s) == 0 for s in self.animals_by_role.values()):
            self.root = self._choose_initial_root(base_midi)
            print("Global root set to:", self.root)