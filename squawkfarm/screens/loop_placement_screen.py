from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.core.window import Window
from kivy.graphics import Rectangle

from imslib.screen import Screen

from squawkfarm.services.loop_engine import LoopEngine
from squawkfarm.ui.loop_grid import LoopGrid
from squawkfarm.utils import get_ui_asset_path
from squawkfarm.widgets.animal_piano import AnimalPiano, AnimalPianoNote

# TODO: move to pitch file & import
MAJOR_OFFSETS = [0, 2, 4, 5, 7, 9, 11, 12]   # C D E F G A B C
MINOR_OFFSETS = [0, 2, 3, 5, 7, 8, 10, 12]   # natural minor example

# TODO: Maxine, change to the correct octave!
def get_octave_c_for_animal(base_midi: int) -> int:
    c_down = base_midi - (base_midi % 12)
    c_up = c_down + 12
    return c_down if abs(base_midi - c_down) <= abs(base_midi - c_up) else c_up

class LoopPlacementScreen(Screen):
    def __init__(self, **kwargs):
        super(LoopPlacementScreen, self).__init__(**kwargs)
        self.loop_engine: LoopEngine = Screen.globals.loop_engine

        self.grid_x_margin = Window.width * 0.08
        self.grid_y_margin = Window.height * 0.18

        # Piano overlay
        self.piano = AnimalPiano()
        # We'll set pos/size in on_enter / on_resize

        # drag state for notes
        self._drag_note = None
        self._drag_offset = (0.0, 0.0)        # where inside the note we grabbed it
        self._drag_note_start_slot = None

        # Barn + sample buttons (same as before)
        self.barn_path = get_ui_asset_path("barn4.png")
        self.barn = Image(source=self.barn_path).texture
        self.barn_btn_size = Window.width / 8
        self.barn_btn = Button(
            size_hint=(None, None),
            size=(self.barn_btn_size, self.barn_btn_size),
            pos=(Window.width - self.barn_btn_size, 0),
            background_normal="",
            background_color=(1, 1, 1, 0),
        )
        with self.barn_btn.canvas.before:
            self.barn_rect = Rectangle(
                pos=self.barn_btn.pos,
                size=self.barn_btn.size,
                texture=self.barn,
            )
        self.barn_btn.bind(on_press=self._on_barn_press)

        self.sample_button = Button(
            text="Sample",
            size_hint=(None, None),
            size=(100, 50),
            pos=(Window.width / 2 - 50, Window.height - 60),
        )
        self.sample_button.bind(on_press=self._on_sample_press)

    def _add_button_widgets(self):
        self.add_widget(self.sample_button)
        self.add_widget(self.barn_btn)

    def _remove_button_widgets(self):
        self.remove_widget(self.sample_button)
        self.remove_widget(self.barn_btn)

    # ---------------- Lifecycle ---------------- #

    def on_enter(self, animal_id: str):
        self.animal_id = animal_id
        self.canvas.before.clear()
        self.canvas.clear()

        # Grid behind everything in canvas.before
        self.grid = LoopGrid(
            total_slots=self.loop_engine.get_total_slots(),
            slots_per_beat=self.loop_engine.get_slots_per_beat(),
            slots_per_measure=self.loop_engine.get_slots_per_measure(),
            x_margin=self.grid_x_margin,
            y_margin=self.grid_y_margin,
            draw_rows=True,
        )
        self.canvas.before.add(self.grid)

        # Piano overlay spans whole window, anchored at (0,0)
        self.piano.size = Window.size
        self.piano.pos = (0, 0)
        if self.piano.parent:
            self.remove_widget(self.piano)
        self.add_widget(self.piano)

        self._rebuild_piano_from_engine()
        self._add_button_widgets()


    def on_resize(self, winsize):
        self.sample_button.pos = (Window.width / 2 - 50, Window.height - 60)
        self.barn_btn.size = (Window.width / 8, Window.width / 8)
        self.barn_btn.pos = (Window.width - self.barn_btn.width, 0)
        self.barn_rect.size = self.barn_btn.size
        self.barn_rect.pos = self.barn_btn.pos

        if hasattr(self, "grid"):
            self.grid.on_resize(winsize)
            self._rebuild_piano_from_engine()

        self.piano.size = Window.size
        self.piano.pos = (0, 0)


    def on_update(self):
        self.loop_engine.on_update()

    def on_exit(self):
        self._remove_button_widgets()
        self.loop_engine.pause()

    def _on_barn_press(self, *_):
        self.switch_to("garden")

    def _on_sample_press(self, *_):
        self.loop_engine.pause()
        self.loop_engine.play()
        
        # ---------------- Pitch row helpers ---------------- #

    def row_to_midi(self, row: int, base_midi: int, key_mode: str) -> int:
        octave_c = get_octave_c_for_animal(base_midi)
        offsets = MAJOR_OFFSETS if key_mode == "major" else MINOR_OFFSETS
        row = max(0, min(7, row))
        return octave_c + offsets[row]
    
    def midi_to_row(self, midi: int, base_midi: int, key_mode: str) -> int:
        octave_c = get_octave_c_for_animal(base_midi)
        offsets = MAJOR_OFFSETS if key_mode == "major" else MINOR_OFFSETS
        semitone_offset = midi - octave_c
        row = min(range(8), key=lambda i: abs(offsets[i] - semitone_offset))
        return row
    
    def _rebuild_piano_from_engine(self):
        """Clear and redraw all notes from LoopEngine.loop instances."""
        self.piano.clear_notes()
        
        height = self.grid.slot_height()
        instances = self.loop_engine.get_instances_info(self.animal_id)

        base_midi = self.loop_engine.get_base_midi(self.animal_id)
        key_mode = self.loop_engine.get_key_mode()

        for start_slot, num_slots, midi in instances:
            x = self.grid.slot_index_to_x(start_slot)        # window X
            width = self.grid.slots_to_pixels(num_slots)
            row = self.midi_to_row(midi, base_midi, key_mode)
            y = self.grid.slot_index_to_y(row)               # window Y

            note = self.piano.add_note(
                x=x,
                y=y,
                width=width,
                height=height,
            )

            note.start_slot = start_slot
            note.midi = midi
            
        # ---------------- Dragging ---------------- #

    def on_touch_down(self, touch):
        # Let buttons etc handle it first
        if super().on_touch_down(touch):
            return True

        # Hit-test notes (reverse so topmost wins)
        for note in reversed(self.piano.notes):
            nx, ny = note.pos
            w, h = note.size
            if nx <= touch.x <= nx + w and ny <= touch.y <= ny + h:
                self._drag_note = note
                # store offset from note origin to touch point
                self._drag_offset = (touch.x - nx, touch.y - ny)
                self._drag_note_start_slot = getattr(note, "start_slot", None)

                # simple selection
                self.piano.set_selected(note)
                return True

        return False


    def on_touch_move(self, touch):
        if not self._drag_note:
            return super().on_touch_move(touch)

        off_x, off_y = self._drag_offset

        # Desired top-left in window coords
        new_x = touch.x - off_x
        new_y = touch.y - off_y

        # Clamp inside the grid in window coords
        new_x = max(self.grid.x,
                    min(new_x, self.grid.x + self.grid.width - self._drag_note.size[0]))
        new_y = max(self.grid.y,
                    min(new_y, self.grid.y + self.grid.height - self._drag_note.size[1]))

        self._drag_note.set_position(new_x, new_y)
        return True


    def on_touch_up(self, touch):
        if not self._drag_note:
            return super().on_touch_up(touch)

        note = self._drag_note
        self._drag_note = None

        old_start_slot = self._drag_note_start_slot

        # use grid to snap
        column = self.grid.x_to_slot_index(note.pos[0])
        row = self.grid.y_to_slot_index(note.pos[1])

        # move instance in engine (no overlap)
        final_column = self.loop_engine.slide_instance(
            self.animal_id,
            old_start_slot,
            column,
            overlap=False,
        )
        note.start_slot = final_column

        # update pitch from row
        final_midi = self.row_to_midi(
            row,
            self.loop_engine.get_base_midi(self.animal_id),
            self.loop_engine.get_key_mode(),
        )
        self.loop_engine.set_pitch_of_instance(self.animal_id, final_column, final_midi)

        # rebuild for full sync
        self._rebuild_piano_from_engine()
        return True




