import os

from kivy.uix.button import Button
from kivy.uix.widget import Widget
from kivy.uix.image import Image
from kivy.core.window import Window
from kivy.graphics import Rectangle, Color

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

        # Add button - creates a new note to drag onto the grid
        self.add_button = Button(
            text="Add",
            size_hint=(None, None),
            size=(80, 50),
            pos=(20, Window.height - 60),
        )
        self.add_button.bind(on_press=self._on_add_press)

        # Delete button - spawns a hammer for deletion
        self.delete_button = Button(
            text="Delete",
            size_hint=(None, None),
            size=(80, 50),
            pos=(110, Window.height - 60),
        )
        self.delete_button.bind(on_press=self._on_delete_press)

        # Track if we're adding a new note
        self._adding_note = False
        self._new_note = None

        # Track hammer for deletion
        self._hammer_active = False
        self._hammer_widget = None
        self._dragging_hammer = False
        self._hammer_offset = (0.0, 0.0)

    def _add_button_widgets(self):
        self.add_widget(self.sample_button)
        self.add_widget(self.add_button)
        self.add_widget(self.delete_button)
        self.add_widget(self.barn_btn)

    def _remove_button_widgets(self):
        self.remove_widget(self.sample_button)
        self.remove_widget(self.add_button)
        self.remove_widget(self.delete_button)
        self.remove_widget(self.barn_btn)

    # ---------------- Lifecycle ---------------- #

    def on_enter(self, animal_id: str):
        self.animal_id = animal_id
        self.canvas.before.clear()
        self.canvas.clear()

        Window.bind(on_key_down=self._on_keyboard_down)

        # Add layered backgrounds: lawn.png then board.png on top
        with self.canvas.before:
            Color(1, 1, 1, 1)
            lawn_path = get_ui_asset_path("lawn.png")
            lawn_tex = Image(source=lawn_path).texture if os.path.exists(lawn_path) else None
            if lawn_tex:
                Rectangle(pos=(0, 0), size=Window.size, texture=lawn_tex)

          
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
        self.add_button.pos = (20, Window.height - 60)
        self.delete_button.pos = (110, Window.height - 60)
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
        Window.unbind(on_key_down=self._on_keyboard_down)

        self._remove_button_widgets()
        self.loop_engine.pause()

        if self._adding_note and self._new_note:
            self.piano.remove_note(self._new_note)
            self._adding_note = False
            self._new_note = None

        if self._hammer_active and self._hammer_widget:
            self.remove_widget(self._hammer_widget)
            self._hammer_active = False
            self._hammer_widget = None

    def _on_keyboard_down(self, _window, key, *_args):
        if key == 27:
            if self._hammer_active and self._hammer_widget:
                self.remove_widget(self._hammer_widget)
                self._hammer_active = False
                self._hammer_widget = None
                self._dragging_hammer = False
                return True
        return False

    def _on_barn_press(self, *_):
        self.switch_to("garden")

    def _on_sample_press(self, *_):
        self.loop_engine.pause()
        self.loop_engine.play()

    def _on_add_press(self, *_):
        """Create a new note rectangle that can be dragged onto the grid."""
        if self._adding_note:
            return  # Already adding a note

        # Get loop duration to determine note width
        loop_slots = self.loop_engine.grid.frame_to_slot(
            self.loop_engine.loops[self.animal_id].num_frames
        )
        width = self.grid.slots_to_pixels(loop_slots)
        height = self.grid.slot_height()

        # Get base MIDI and place at middle row (row 3-4)
        base_midi = self.loop_engine.get_base_midi(self.animal_id)
        key_mode = self.loop_engine.get_key_mode()
        midi = self.row_to_midi(3, base_midi, key_mode)

        # Create note in the center of the screen
        x = Window.width / 2 - width / 2
        y = Window.height / 2 - height / 2

        # Add note with a distinct color to show it's being added
        note = self.piano.add_note(x=x, y=y, width=width, height=height)
        note.start_slot = None  # Mark as new (not yet placed)
        note.midi = midi
        note.set_color((1.0, 0.5, 0.5, 0.8))  # Red-ish tint to show it's new

        self._adding_note = True
        self._new_note = note
        self.piano.set_selected(note)

    def _on_delete_press(self, *_):
        if self._hammer_active:
            if self._hammer_widget:
                self.remove_widget(self._hammer_widget)
            self._hammer_active = False
            self._hammer_widget = None
            return

        hammer_path = get_ui_asset_path("hammer.png")
        if not os.path.exists(hammer_path):
            print(f"Warning: hammer.png not found at {hammer_path}")
            return

        hammer_tex = Image(source=hammer_path).texture
        hammer_size = 60

        hammer_widget = Widget()
        hammer_widget.size_hint = (None, None)
        hammer_widget.size = (hammer_size, hammer_size)

        mouse_pos = Window.mouse_pos
        hammer_widget.pos = (mouse_pos[0] - hammer_size / 2, mouse_pos[1] - hammer_size / 2)

        with hammer_widget.canvas:
            Color(1, 1, 1, 1)
            hammer_widget.rect = Rectangle(pos=hammer_widget.pos, size=hammer_widget.size, texture=hammer_tex)

        self._hammer_widget = hammer_widget
        self.add_widget(self._hammer_widget)
        self._hammer_active = True
        self._dragging_hammer = True

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
        if super().on_touch_down(touch):
            return True

        if self._hammer_active and self._hammer_widget:
            hx, hy = self._hammer_widget.pos
            hw, hh = self._hammer_widget.size
            hammer_center_x = hx + hw / 2
            hammer_center_y = hy + hh / 2

            for note in reversed(self.piano.notes):
                nx, ny = note.pos
                w, h = note.size
                if nx <= hammer_center_x <= nx + w and ny <= hammer_center_y <= ny + h:
                    if note.start_slot is not None:
                        self.loop_engine.remove_loop_instance(self.animal_id, note.start_slot)

                    self.piano.remove_note(note)

                    if note == self._new_note:
                        self._adding_note = False
                        self._new_note = None

                    self._rebuild_piano_from_engine()
                    return True
            return True

        for note in reversed(self.piano.notes):
            nx, ny = note.pos
            w, h = note.size
            if nx <= touch.x <= nx + w and ny <= touch.y <= ny + h:
                self._drag_note = note
                self._drag_offset = (touch.x - nx, touch.y - ny)
                self._drag_note_start_slot = getattr(note, "start_slot", None)

                self.piano.set_selected(note)
                return True

        return False


    def on_touch_move(self, touch):
        if self._hammer_active and self._hammer_widget:
            hammer_size = self._hammer_widget.size[0]
            new_x = touch.x - hammer_size / 2
            new_y = touch.y - hammer_size / 2
            self._hammer_widget.pos = (new_x, new_y)
            self._hammer_widget.rect.pos = (new_x, new_y)
            return True

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
        if self._hammer_active:
            return True

        if not self._drag_note:
            return super().on_touch_up(touch)

        note = self._drag_note
        self._drag_note = None

        old_start_slot = self._drag_note_start_slot

        # use grid to snap
        column = self.grid.x_to_slot_index(note.pos[0])
        row = self.grid.y_to_slot_index(note.pos[1])

        # Calculate final MIDI from row
        final_midi = self.row_to_midi(
            row,
            self.loop_engine.get_base_midi(self.animal_id),
            self.loop_engine.get_key_mode(),
        )

        # If this is a new note being added
        if old_start_slot is None:
            # Try to add it to the grid
            success = self.loop_engine.add_loop_instance(
                self.animal_id,
                column,
                overlap=False,
                midi=final_midi
            )

            if success:
                self._adding_note = False
                self._new_note = None
                self._rebuild_piano_from_engine()
                self.loop_engine.play_note_preview(self.animal_id, column)
            else:
                self.piano.remove_note(note)
                self._adding_note = False
                self._new_note = None
                self._rebuild_piano_from_engine()

            return True

        final_column = self.loop_engine.slide_instance(
            self.animal_id,
            old_start_slot,
            column,
            overlap=False,
        )
        note.start_slot = final_column

        self.loop_engine.set_pitch_of_instance(self.animal_id, final_column, final_midi)

        self._rebuild_piano_from_engine()
        self.loop_engine.play_note_preview(self.animal_id, final_column)
        return True




