import os

from kivy.uix.button import Button
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.widget import Widget
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.core.window import Window
from kivy.graphics import Rectangle, Color
from kivy.clock import Clock

from squawkfarm.services.loop_engine import LoopEngine
from squawkfarm.ui.nowbar import NowBar


class ImageButton(ButtonBehavior, Image):
    pass


class ShadowButton(Button):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._shadow_rect = None
        self.bind(pos=self._update_shadow, size=self._update_shadow)
        self._update_shadow()

    def _update_shadow(self, *args):
        if self._shadow_rect:
            self.canvas.before.remove(self._shadow_rect)
            self._shadow_rect = None

        with self.canvas.before:
            Color(0.15, 0.1, 0.05, 0.7)
            self._shadow_rect = Rectangle(
                pos=(self.x + 5, self.y - 5),
                size=self.size
            )

from imslib.screen import Screen

from squawkfarm.ui.loop_grid import LoopGrid
from squawkfarm.utils import get_ui_asset_path
from squawkfarm.widgets.animal_piano import AnimalPiano

MAJOR_OFFSETS = [0, 2, 4, 5, 7, 9, 11, 12]
MINOR_OFFSETS = [0, 2, 3, 5, 7, 8, 10, 12]


def quantize_to_beat_slots(num_slots, slots_per_beat):
    beats = num_slots / slots_per_beat
    if beats < 0.75:
        quantized_beats = 0.5
    elif beats < 1.5:
        quantized_beats = 1
    elif beats < 3.0:
        quantized_beats = 2
    else:
        quantized_beats = 4
    return quantized_beats * slots_per_beat


def get_octave_c_for_animal(base_midi):
    c_down = base_midi - (base_midi % 12)
    c_up = c_down + 12
    return c_down if abs(base_midi - c_down) <= abs(base_midi - c_up) else c_up

class LoopPlacementScreen(Screen):
    def __init__(self, **kwargs):
        super(LoopPlacementScreen, self).__init__(**kwargs)
        self.loop_engine: LoopEngine = Screen.globals.loop_engine

        self.grid_x_margin = Window.width * 0.1
        self.grid_y_margin = Window.height * 0.15

        self.piano = AnimalPiano()

        self._drag_note = None
        self._drag_offset = (0.0, 0.0)
        self._drag_note_start_slot = None

        self.barn_path = get_ui_asset_path("barn.png")
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

        # Trash button in bottom left corner (same size as barn)
        self.trash_path = get_ui_asset_path("trash.png")
        self.trash_texture = Image(source=self.trash_path).texture
        self.trash_btn = Button(
            size_hint=(None, None),
            size=(self.barn_btn_size, self.barn_btn_size),
            pos=(0, 0),
            background_normal="",
            background_color=(1, 1, 1, 0),
        )
        with self.trash_btn.canvas.before:
            self.trash_rect = Rectangle(
                pos=self.trash_btn.pos,
                size=self.trash_btn.size,
                texture=self.trash_texture,
            )

        self.play_icon_path = get_ui_asset_path("play.png")
        self.pause_icon_path = get_ui_asset_path("pause.png")
        self.sample_btn_size = 80
        self.sample_button = ImageButton(
            source=self.play_icon_path,
            size_hint=(None, None),
            size=(self.sample_btn_size, self.sample_btn_size),
            pos=(Window.width / 2 - self.sample_btn_size / 2, Window.height - self.sample_btn_size - 10),
        )
        self.sample_button.bind(on_press=self._on_sample_press)

        self.octave_btn_size = 100
        self.up_icon_path = get_ui_asset_path("up.png")
        self.down_icon_path = get_ui_asset_path("down.png")

        self.octave_label = Label(
            text="",
            size_hint=(None, None),
            size=(120, 50),
            pos=(Window.width - 340, Window.height - 60),
            color=(1, 0.4, 0.7, 1),
        )

        self.octave_up_button = ImageButton(
            source=self.up_icon_path,
            size_hint=(None, None),
            size=(self.octave_btn_size, self.octave_btn_size),
            pos=(Window.width - 110, Window.height - self.octave_btn_size - 10),
        )
        self.octave_up_button.bind(on_touch_down=self._on_octave_up_touch_down, on_touch_up=self._on_octave_up_touch_up)

        self.octave_down_button = ImageButton(
            source=self.down_icon_path,
            size_hint=(None, None),
            size=(self.octave_btn_size, self.octave_btn_size),
            pos=(Window.width - 220, Window.height - self.octave_btn_size - 10),
        )
        self.octave_down_button.bind(on_touch_down=self._on_octave_down_touch_down, on_touch_up=self._on_octave_down_touch_up)

        self.volume_btn_size = 100
        self.plus_icon_path = get_ui_asset_path("plus.png")
        self.minus_icon_path = get_ui_asset_path("minus.png")

        self.volume_label = Label(
            text="",
            size_hint=(None, None),
            size=(100, 50),
            pos=(Window.width / 4 - 50, Window.height - 60),
            color=(0.4, 0.7, 1, 1),
            opacity=0,
        )
        self.volume_up_button = ImageButton(
            source=self.plus_icon_path,
            size_hint=(None, None),
            size=(self.volume_btn_size, self.volume_btn_size),
            pos=(Window.width / 4 + 10, Window.height - self.volume_btn_size - 10),
        )
        self.volume_up_button.bind(on_press=self._on_volume_up_press)

        self.volume_down_button = ImageButton(
            source=self.minus_icon_path,
            size_hint=(None, None),
            size=(self.volume_btn_size, self.volume_btn_size),
            pos=(Window.width / 4 - self.volume_btn_size - 10, Window.height - self.volume_btn_size - 10),
        )
        self.volume_down_button.bind(on_press=self._on_volume_down_press)

        self.add_button = ShadowButton(
            text="[b]Add[/b]",
            markup=True,
            size_hint=(None, None),
            size=(120, 80),
            pos=(20, Window.height - 90),
            background_normal='',
            background_down='',
            background_color=(1, 0.75, 0.85, 1),
            color=(0.05, 0.05, 0.3, 1),
            font_size=18,
        )
        self.add_button.bind(on_press=self._on_add_press)

        self.delete_button = ShadowButton(
            text="[b]Delete[/b]",
            markup=True,
            size_hint=(None, None),
            size=(120, 80),
            pos=(150, Window.height - 90),
            background_normal='',
            background_down='',
            background_color=(1, 0.75, 0.85, 1),
            color=(0.05, 0.05, 0.3, 1),
            font_size=18,
        )
        self.delete_button.bind(on_press=self._on_delete_press)

        self._adding_note = False
        self._new_note = None

        self._hammer_active = False
        self._hammer_widget = None
        self._dragging_hammer = False
        self._hammer_offset = (0.0, 0.0)
        
        # Octave shifting state
        self._octave_shift_active = False
        self._octave_shift_direction = 0  # 1 for up, -1 for down
        self._octave_shift_event = None

        # Toggle Sequence button
        self.toggle_sequence_btn = ShadowButton(
            text="[b]Toggle Sequence[/b]",
            markup=True,
            size_hint=(None, None),
            size=(220, 80),
            pos=(Window.width / 2 - 110, 20),
            background_normal='',
            background_down='',
            background_color=(0.8, 0.9, 1, 1),
            color=(0.05, 0.05, 0.3, 1),
            font_size=20,
        )
        self.toggle_sequence_btn.bind(on_press=self._on_toggle_sequence_press)
        
        self.nowbar = None
        self.playing_preview = False

    def _add_button_widgets(self):
        self.add_widget(self.sample_button)
        self.add_widget(self.octave_label)
        self.add_widget(self.octave_up_button)
        self.add_widget(self.octave_down_button)
        self.add_widget(self.volume_label)
        self.add_widget(self.volume_up_button)
        self.add_widget(self.volume_down_button)
        self.add_widget(self.add_button)
        self.add_widget(self.delete_button)
        self.add_widget(self.barn_btn)
        self.add_widget(self.trash_btn)
        self.add_widget(self.toggle_sequence_btn)

    def _remove_button_widgets(self):
        self.remove_widget(self.sample_button)
        self.remove_widget(self.octave_label)
        self.remove_widget(self.octave_up_button)
        self.remove_widget(self.octave_down_button)
        self.remove_widget(self.volume_label)
        self.remove_widget(self.volume_up_button)
        self.remove_widget(self.volume_down_button)
        self.remove_widget(self.add_button)
        self.remove_widget(self.delete_button)
        self.remove_widget(self.barn_btn)
        self.remove_widget(self.trash_btn)
        self.remove_widget(self.toggle_sequence_btn)

    def _on_toggle_sequence_press(self, *_):
        self.loop_engine.toggle_rhythm_option(self.animal_id)
        self._rebuild_piano_from_engine()

    def on_enter(self, animal_id):
        self.animal_id = animal_id
        self.canvas.before.clear()
        self.canvas.clear()

        Window.bind(on_key_down=self._on_keyboard_down)

        with self.canvas.before:
            Color(1, 1, 1, 1)
            lawn_path = get_ui_asset_path("lawn.png")
            lawn_tex = Image(source=lawn_path).texture if os.path.exists(lawn_path) else None
            if lawn_tex:
                self.bg_rect = Rectangle(pos=(0, 0), size=Window.size, texture=lawn_tex)

        self.grid = LoopGrid(
            total_slots=self.loop_engine.get_total_slots(),
            slots_per_beat=self.loop_engine.get_slots_per_beat(),
            slots_per_measure=self.loop_engine.get_slots_per_measure(),
            x_margin=self.grid_x_margin,
            y_margin=self.grid_y_margin,
            draw_rows=True,
            skip_outer_lines=True,
        )
        self.canvas.before.add(self.grid)
        
        self.duration = self.loop_engine.slot_to_time(self.loop_engine.get_total_slots())

        self.piano.size = Window.size
        self.piano.pos = (0, 0)
        if self.piano.parent:
            self.remove_widget(self.piano)
        self.add_widget(self.piano)

        self._rebuild_piano_from_engine()
        self._add_button_widgets()
        self._update_volume_label()


    def on_resize(self, winsize):
        # Resize background
        if hasattr(self, 'bg_rect'):
            self.bg_rect.pos = (0, 0)
            self.bg_rect.size = Window.size
        
        self.sample_btn_size = 80
        self.sample_button.size = (self.sample_btn_size, self.sample_btn_size)
        self.sample_button.pos = (Window.width / 2 - self.sample_btn_size / 2, Window.height - self.sample_btn_size - 10)
        
        self.octave_btn_size = 100
        self.octave_up_button.size = (self.octave_btn_size, self.octave_btn_size)
        self.octave_up_button.pos = (Window.width - 110, Window.height - self.octave_btn_size - 10)
        self.octave_down_button.size = (self.octave_btn_size, self.octave_btn_size)
        self.octave_down_button.pos = (Window.width - 220, Window.height - self.octave_btn_size - 10)
        self.octave_label.pos = (Window.width - 340, Window.height - 60)
        
        self.volume_btn_size = 100
        self.volume_up_button.size = (self.volume_btn_size, self.volume_btn_size)
        self.volume_up_button.pos = (Window.width / 4 + 10, Window.height - self.volume_btn_size - 10)
        self.volume_down_button.size = (self.volume_btn_size, self.volume_btn_size)
        self.volume_down_button.pos = (Window.width / 4 - self.volume_btn_size - 10, Window.height - self.volume_btn_size - 10)
        self.volume_label.pos = (Window.width / 4 - 50, Window.height - 60)
        
        self.add_button.pos = (20, Window.height - 90)
        self.delete_button.pos = (150, Window.height - 90)
        self.barn_btn.size = (Window.width / 8, Window.width / 8)
        self.barn_btn.pos = (Window.width - self.barn_btn.width, 0)
        self.barn_rect.size = self.barn_btn.size
        self.barn_rect.pos = self.barn_btn.pos
        # Resize trash button (same size as barn, bottom left)
        self.trash_btn.size = (Window.width / 8, Window.width / 8)
        self.trash_btn.pos = (0, 0)
        self.trash_rect.size = self.trash_btn.size
        self.trash_rect.pos = self.trash_btn.pos

        if hasattr(self, "grid"):
            self.grid.x_margin = Window.width * 0.1
            self.grid.y_margin = Window.height * 0.15
            self.grid.on_resize(winsize)
            self._rebuild_piano_from_engine()

        self.piano.size = Window.size
        self.piano.pos = (0, 0)
        
        if self.nowbar:
            self.nowbar.on_resize(self.grid.x, self.grid.x + self.grid.width, self.grid.y, self.grid.y + self.grid.height)

    def _stop_preview(self):
        self.sample_button.source = self.play_icon_path
        self.playing_preview = False
        if self.loop_engine.is_playing():
            self.loop_engine.pause()

    def on_update(self):
        self.loop_engine.on_update()
        
        if self.nowbar:
            if self.loop_engine.is_playing():
                self.nowbar.on_update(Clock.frametime)
            elif self.playing_preview:
                self.nowbar.current_time = self.duration
                self._stop_preview()

    def on_exit(self):
        Window.unbind(on_key_down=self._on_keyboard_down)

        self._remove_button_widgets()
        self._stop_continuous_octave_shift()
        self._destroy_nowbar()
        self._stop_preview()

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
        
    def _start_preview(self, start_time=0.0):
        self._ensure_nowbar()
        self.loop_engine.play(start_time, animal_id=self.animal_id)
        self.sample_button.source = self.pause_icon_path
        self.playing_preview = True
        
    def _ensure_nowbar(self):
        if self.nowbar is None:
            self.nowbar = NowBar(
                duration=self.duration,
                start_x=self.grid.x,
                end_x=self.grid.x + self.grid.width,
                bottom_y=self.grid.y,
                top_y=self.grid.y + self.grid.height,
            )
            print("Nowbar variables: ", self.nowbar.duration, self.nowbar.start_x, self.nowbar.end_x,)
            self.canvas.after.add(self.nowbar)

    def _destroy_nowbar(self):
        if self.nowbar:
            self.canvas.after.remove(self.nowbar)
            self.nowbar = None
            self.playing_preview = False

    def _on_sample_press(self, *_):
        if self.loop_engine.is_playing():
            self.loop_engine.pause()
            self._stop_preview()
        else:
            start_time = 0.0
            if self.nowbar:
                if self.nowbar.current_time < self.duration:
                    start_time = self.nowbar.current_time
                else:
                    self.nowbar.reset()

            self._start_preview(start_time)

    def _on_volume_up_press(self, *_):
        """Increase volume of this animal's loop"""
        loop = self.loop_engine.loops.get(self.animal_id)
        if loop:
            new_vol = min(1.0, loop.volume + 0.1)
            loop.set_volume(new_vol)
            self._update_volume_label()

    def _on_volume_down_press(self, *_):
        """Decrease volume of this animal's loop"""
        loop = self.loop_engine.loops.get(self.animal_id)
        if loop:
            new_vol = max(0.0, loop.volume - 0.1)
            loop.set_volume(new_vol)
            self._update_volume_label()

    def _update_volume_label(self):
        """Update the volume label to show current volume"""
        loop = self.loop_engine.loops.get(self.animal_id)
        if loop:
            self.volume_label.text = f"Vol: {loop.volume:.1f}"
        else:
            self.volume_label.text = ""

    def _on_octave_up_touch_down(self, button, touch):
        if button.collide_point(*touch.pos):
            self._octave_shift_active = True
            self._octave_shift_direction = 1
            self._start_continuous_octave_shift()
            return True
        return False

    def _on_octave_up_touch_up(self, button, touch):
        self._octave_shift_active = False
        self._stop_continuous_octave_shift()
        return True

    def _on_octave_down_touch_down(self, button, touch):
        if button.collide_point(*touch.pos):
            self._octave_shift_active = True
            self._octave_shift_direction = -1
            self._start_continuous_octave_shift()
            return True
        return False

    def _on_octave_down_touch_up(self, button, touch):
        self._octave_shift_active = False
        self._stop_continuous_octave_shift()
        return True

    def _start_continuous_octave_shift(self):
        """Schedule continuous octave shifting"""
        from kivy.clock import Clock
        
        # Cancel any existing scheduled event
        if self._octave_shift_event:
            self._octave_shift_event.cancel()
        
        # Perform first shift immediately
        self._do_octave_shift()
        
        # Then schedule repeated shifts every 0.1 seconds
        self._octave_shift_event = Clock.schedule_interval(
            lambda dt: self._do_octave_shift(),
            0.1
        )

    def _stop_continuous_octave_shift(self):
        """Cancel continuous octave shifting"""
        if self._octave_shift_event:
            self._octave_shift_event.cancel()
            self._octave_shift_event = None

    def _do_octave_shift(self):
        """Perform a single octave shift"""
        self.loop_engine.shift_animal_octave(self.animal_id, self._octave_shift_direction)
        self._rebuild_piano_from_engine()
        self._stop_preview()
        self._destroy_nowbar()
        self._start_preview()

    def _on_add_press(self, *_):
        if self._adding_note:
            return

        loop_slots = self.loop_engine.grid.frame_to_slot(
            self.loop_engine.loops[self.animal_id].num_frames
        )
        quantized_slots = quantize_to_beat_slots(loop_slots, self.loop_engine.get_slots_per_beat())
        
        width = self.grid.slots_to_pixels(quantized_slots)
        height = self.grid.slot_height()

        base_midi = self.loop_engine.get_base_midi(self.animal_id)
        key_mode = self.loop_engine.get_key_mode()
        midi = self.row_to_midi(3, base_midi, key_mode)

        x = Window.width / 2 - width / 2
        y = Window.height / 2 - height / 2

        note = self.piano.add_note(x=x, y=y, width=width, height=height)
        note.start_slot = None
        note.midi = midi
        note.set_color((1.0, 0.5, 0.5, 0.8))

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
            return

        hammer_tex = Image(source=hammer_path).texture
        hammer_size = 120

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

    def row_to_midi(self, row: int, base_midi: int, key_mode: str) -> int:
        if key_mode == "major":
            intervals = [0, 2, 4, 5, 7, 9, 11]
        else:
            intervals = [0, 2, 3, 5, 7, 8, 10]

        row = max(0, min(7, row))
        step_index = row
        degree = step_index % len(intervals)
        octave_offset = step_index // len(intervals)
        offset = intervals[degree] + 12 * octave_offset
        note = base_midi + offset
        note = max(0, min(127, note))
        return note

    def midi_to_row(self, midi: int, base_midi: int, key_mode: str) -> int:
        if key_mode == "major":
            intervals = [0, 2, 4, 5, 7, 9, 11]
        else:
            intervals = [0, 2, 3, 5, 7, 8, 10]

        offsets = []
        for row in range(8):
            degree = row % len(intervals)
            octave_offset = row // len(intervals)
            offset = intervals[degree] + 12 * octave_offset
            offsets.append(offset)

        semitone_offset = midi - base_midi
        row = min(range(8), key=lambda i: abs(offsets[i] - semitone_offset))
        return row

    def _rebuild_piano_from_engine(self):
        self.piano.clear_notes()

        height = self.grid.slot_height()
        instances, num_slots = self.loop_engine.get_instances_info(self.animal_id)

        base_midi = self.loop_engine.get_base_midi(self.animal_id)
        key_mode = self.loop_engine.get_key_mode()
        slots_per_beat = self.loop_engine.get_slots_per_beat()

        for start_slot, midi in instances.items():
            x = self.grid.slot_index_to_x(start_slot)
            quantized_slots = quantize_to_beat_slots(num_slots, slots_per_beat)
            width = self.grid.slots_to_pixels(quantized_slots)
            row = self.midi_to_row(midi, base_midi, key_mode)
            y = self.grid.slot_index_to_y(row)

            note = self.piano.add_note(
                x=x,
                y=y,
                width=width,
                height=height,
            )

            note.start_slot = start_slot
            note.midi = midi

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

        self._destroy_nowbar()
        self._stop_preview()
        
        off_x, off_y = self._drag_offset

        # Desired top-left in window coords
        new_x = touch.x - off_x
        new_y = touch.y - off_y

        # Allow x to go to 0 (towards trash) but not past right edge of grid
        new_x = max(0,
                    min(new_x, self.grid.x + self.grid.width - self._drag_note.size[0]))
        # Allow y to go down to 0 (towards trash) but not above grid
        new_y = max(0,
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

        # Check if note was dropped in the trash zone
        trash_x, trash_y = self.trash_btn.pos
        trash_w, trash_h = self.trash_btn.size
        note_center_x = note.pos[0] + note.size[0] / 2
        note_center_y = note.pos[1] + note.size[1] / 2

        if (trash_x <= note_center_x <= trash_x + trash_w and
            trash_y <= note_center_y <= trash_y + trash_h):
            # Delete the note
            if old_start_slot is not None:
                self.loop_engine.remove_loop_instance(self.animal_id, old_start_slot)
            self.piano.remove_note(note)
            if note == self._new_note:
                self._adding_note = False
                self._new_note = None
            self._rebuild_piano_from_engine()
            return True

        # If note was dragged below the grid, snap it back to the bottom row
        if note.pos[1] < self.grid.y:
            note.set_position(note.pos[0], self.grid.y)

        # If note was dragged left of the grid, snap it back to the left edge
        if note.pos[0] < self.grid.x:
            note.set_position(self.grid.x, note.pos[1])

        column = self.grid.x_to_slot_index(note.pos[0])
        row = self.grid.y_to_slot_index(note.pos[1])

        final_midi = self.row_to_midi(
            row,
            self.loop_engine.get_base_midi(self.animal_id),
            self.loop_engine.get_key_mode(),
        )

        if old_start_slot is None:
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