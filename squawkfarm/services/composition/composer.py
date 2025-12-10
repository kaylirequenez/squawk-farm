MIN_ROOT = 48  # C3
MAX_ROOT = 72  # C5


class Composer:
    def __init__(self, key_mode, root, chord_progression):
        self.key_mode = key_mode
        self.root = max(MIN_ROOT, min(MAX_ROOT, root))
        self.chord_progression = chord_progression

        self.animals_by_role = {
            "bass": set(),
            "melody": set(),
            "harmony": set(),
        }

    def _choose_initial_root(self, base_midi):
        c_down = base_midi - (base_midi % 12)
        c_up = c_down + 12

        if abs(base_midi - c_down) <= abs(base_midi - c_up):
            nearest_c = c_down
        else:
            nearest_c = c_up

        return max(MIN_ROOT, min(MAX_ROOT, nearest_c))

    def _guess_role_from_pitch(self, animal_midi, root_midi):
        offset = animal_midi - root_midi

        if offset <= -5:
            return "bass"
        elif offset >= 7:
            return "melody"
        else:
            return "harmony"

    def set_key_mode(self, key_mode):
        self.key_mode = key_mode

    def set_root(self, root):
        self.root = max(MIN_ROOT, min(MAX_ROOT, root))

    def set_chord_progression(self, progression):
        self.chord_progression = progression

    def register_animal_role(self, animal_id, role):
        self.animals_by_role[role].add(animal_id)

    def unregister_animal_role(self, animal_id, role):
        self.animals_by_role[role].discard(animal_id)

    def change_animal_role(self, animal_id, old_role, new_role):
        if old_role == new_role:
            return
        self.unregister_animal_role(animal_id, old_role)
        self.register_animal_role(animal_id, new_role)

    def guess_initial_role(self, animal_midi, beats):
        base_role = self._guess_role_from_pitch(animal_midi, self.root)

        bass_count = len(self.animals_by_role.get("bass"))
        melody_count = len(self.animals_by_role.get("melody"))
        offset = animal_midi - self.root

        # Long, sustained phrase + mid/high pitch → more harmony-ish
        if beats >= 3.0:
            if base_role == "melody":
                base_role = "harmony"
            elif base_role == "bass" and offset > -10:
                # not super deep + long → treat as harmonic bed
                base_role = "harmony"

        # Very short phrase + fairly high → more melodic
        if beats <= 1.0:
            if base_role == "harmony" and offset >= 4:
                # short and relatively high → feels like a melodic lick
                base_role = "melody"

        # Keep at least one bass/melody if pitch suggests it
        if bass_count == 0 and base_role == "bass":
            return "bass"
        if melody_count == 0 and base_role == "melody":
            return "melody"

        # If bass is over-represented, push borderline lows toward harmony
        if base_role == "bass" and bass_count >= 2 and -7 <= offset:
            return "harmony"

        if base_role == "melody" and melody_count >= 3 and offset <= 10:
            return "harmony"

        return base_role

    def handle_first_animal_if_needed(self, base_midi):
        if all(len(s) == 0 for s in self.animals_by_role.values()):
            self.root = self._choose_initial_root(base_midi)
