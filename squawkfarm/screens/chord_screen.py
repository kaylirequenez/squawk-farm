import os

from kivy.uix.button import Button
from kivy.uix.widget import Widget
from kivy.uix.label import Label
from kivy.uix.image import Image
from kivy.core.window import Window
from kivy.graphics import Rectangle, Color, Line
from kivy.uix.boxlayout import BoxLayout

from imslib.screen import Screen


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

from squawkfarm.models.progression import Chord, ChordProgression
from squawkfarm.utils import get_ui_asset_path

NOTE_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
NOTE_TO_MIDI_OFFSET = {"C": 0, "C#": 1, "D": 2, "Eb": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "Ab": 8, "A": 9, "Bb": 10, "B": 11}


class ChordSlot(Widget):
    def __init__(self, index, **kwargs):
        super().__init__(**kwargs)
        self.index = index
        self.note = None
        self.quality = "maj"
        self.has_7 = False
        self.selected = False
        self.size_hint = (None, None)
        self._draw()

    def _draw(self):
        self.canvas.clear()
        with self.canvas:
            Color(0.3, 0.25, 0.2, 0.4)
            Rectangle(pos=(self.pos[0] + 3, self.pos[1] - 3), size=self.size)

            if self.selected:
                Color(1, 0.8, 0.4, 1)
            else:
                Color(0.9, 0.85, 0.7, 1)
            Rectangle(pos=self.pos, size=self.size)

            Color(0.4, 0.3, 0.2, 1)
            Line(rectangle=(self.pos[0], self.pos[1], self.size[0], self.size[1]), width=2)

    def set_note(self, note):
        self.note = note
        self._update_label()

    def set_quality(self, quality):
        self.quality = quality
        self._update_label()

    def toggle_7(self):
        self.has_7 = not self.has_7
        self._update_label()

    def set_selected(self, selected):
        self.selected = selected
        self._draw()

    def _update_label(self):
        pass

    def get_chord_text(self):
        if not self.note:
            return ""
        text = self.note
        if self.quality == "min":
            text += "m"
        if self.has_7:
            text += "7"
        return text

    def collide_point(self, x, y):
        return (self.pos[0] <= x <= self.pos[0] + self.size[0] and
                self.pos[1] <= y <= self.pos[1] + self.size[1])


class ChordScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.loop_engine = Screen.globals.loop_engine

        self.slots = []
        self.selected_slot = None
        self.slot_labels = []

        self.dragging_note = None
        self.drag_label = None

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

        self.note_buttons = []
        self.quality_buttons = {}

    def _create_note_buttons(self):
        btn_size = 140
        spacing = 16
        total_width = len(NOTE_NAMES) * btn_size + (len(NOTE_NAMES) - 1) * spacing
        start_x = (Window.width - total_width) / 2
        y = Window.height - 160

        for i, note in enumerate(NOTE_NAMES):
            btn = ShadowButton(
                text=f"[b]{note}[/b]",
                markup=True,
                size_hint=(None, None),
                size=(btn_size, btn_size),
                pos=(start_x + i * (btn_size + spacing), y),
                background_normal='',
                background_down='',
                background_color=(1, 0.75, 0.85, 1),
                color=(0.05, 0.05, 0.3, 1),
                font_size=44,
            )
            btn.note = note
            btn.bind(on_touch_down=self._on_note_touch_down)
            self.note_buttons.append(btn)
            self.add_widget(btn)

    def _create_quality_buttons(self):
        btn_width = 160
        btn_height = 100
        spacing = 30
        y = Window.height - 300

        qualities = [("maj", "maj"), ("min", "min"), ("7", "7")]
        total_width = len(qualities) * btn_width + (len(qualities) - 1) * spacing
        start_x = (Window.width - total_width) / 2

        for i, (key, text) in enumerate(qualities):
            btn = ShadowButton(
                text=f"[b]{text}[/b]",
                markup=True,
                size_hint=(None, None),
                size=(btn_width, btn_height),
                pos=(start_x + i * (btn_width + spacing), y),
                background_normal='',
                background_down='',
                background_color=(1, 0.75, 0.85, 1),
                color=(0.05, 0.05, 0.3, 1),
                font_size=44,
            )
            btn.quality_key = key
            btn.bind(on_press=self._on_quality_press)
            self.quality_buttons[key] = btn
            self.add_widget(btn)

    def _create_slots(self):
        slot_width = 240
        slot_height = 200
        spacing = 40
        total_width = 4 * slot_width + 3 * spacing
        start_x = (Window.width - total_width) / 2
        y = Window.height / 2 - slot_height / 2

        for i in range(4):
            slot = ChordSlot(i)
            slot.size = (slot_width, slot_height)
            slot.pos = (start_x + i * (slot_width + spacing), y)
            slot._draw()
            self.slots.append(slot)
            self.add_widget(slot)

            label = Label(
                text="",
                size_hint=(None, None),
                size=(slot_width, 60),
                pos=(slot.pos[0], slot.pos[1] + slot_height / 2 - 30),
                color=(0.2, 0.15, 0.1, 1),
                font_size=48,
            )
            self.slot_labels.append(label)
            self.add_widget(label)

    def _update_slot_labels(self):
        for i, slot in enumerate(self.slots):
            self.slot_labels[i].text = slot.get_chord_text()

    def on_enter(self, *args):
        self.canvas.before.clear()
        self.canvas.clear()

        with self.canvas.before:
            Color(1, 1, 1, 1)
            lawn_path = get_ui_asset_path("lawn.png")
            lawn_tex = Image(source=lawn_path).texture if os.path.exists(lawn_path) else None
            if lawn_tex:
                Rectangle(pos=(0, 0), size=Window.size, texture=lawn_tex)

        self.slots.clear()
        self.slot_labels.clear()
        self.note_buttons.clear()
        self.quality_buttons.clear()

        self._create_note_buttons()
        self._create_quality_buttons()
        self._create_slots()

        self.add_widget(self.barn_btn)

        self._load_current_progression()

    def _load_current_progression(self):
        progression = self.loop_engine.get_chord_progression()
        if not progression:
            return

        for i, slot in enumerate(self.slots):
            if i < len(progression.chords):
                chord = progression.chords[i]
                degree = chord.degree
                note_idx = (degree - 1) % 12
                slot.note = NOTE_NAMES[note_idx]
                slot.quality = chord.quality if chord.quality in ("maj", "min") else "maj"
                slot.has_7 = "7" in chord.quality
                slot._draw()

        self._update_slot_labels()

    def on_exit(self):
        self._apply_progression()

        for btn in self.note_buttons:
            self.remove_widget(btn)
        for btn in self.quality_buttons.values():
            self.remove_widget(btn)
        for slot in self.slots:
            self.remove_widget(slot)
        for label in self.slot_labels:
            self.remove_widget(label)
        self.remove_widget(self.barn_btn)

        if self.drag_label:
            self.remove_widget(self.drag_label)
            self.drag_label = None

    def on_resize(self, winsize):
        self.barn_btn.size = (Window.width / 8, Window.width / 8)
        self.barn_btn.pos = (Window.width - self.barn_btn.width, 0)
        self.barn_rect.size = self.barn_btn.size
        self.barn_rect.pos = self.barn_btn.pos

    def _on_barn_press(self, *_):
        self.switch_to("garden")

    def _apply_progression(self):
        chords = []
        for slot in self.slots:
            if slot.note:
                quality = slot.quality
                if slot.has_7:
                    quality = quality + "7" if quality != "maj" else "dom7"

                semitone = NOTE_TO_MIDI_OFFSET[slot.note]
                degree = semitone + 1

                chords.append(Chord(degree=degree, quality=quality))
            else:
                chords.append(Chord(degree=1, quality="maj"))

        if chords:
            progression = ChordProgression(chords)
            self.loop_engine.set_chord_progression(progression)

    def _on_note_touch_down(self, btn, touch):
        if not btn.collide_point(*touch.pos):
            return False

        self.dragging_note = btn.note
        self.drag_label = Label(
            text=btn.note,
            size_hint=(None, None),
            size=(60, 60),
            pos=(touch.x - 30, touch.y - 30),
            color=(1, 0.4, 0.7, 1),
            font_size=32,
        )
        self.add_widget(self.drag_label)
        touch.grab(self)
        return True

    def _on_quality_press(self, btn):
        if not self.selected_slot:
            return

        key = btn.quality_key
        if key == "7":
            self.selected_slot.toggle_7()
        else:
            self.selected_slot.set_quality(key)

        self._update_slot_labels()

    def on_touch_move(self, touch):
        if touch.grab_current is self and self.drag_label:
            self.drag_label.pos = (touch.x - 30, touch.y - 30)
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)

            if self.drag_label and self.dragging_note:
                for slot in self.slots:
                    if slot.collide_point(touch.x, touch.y):
                        slot.set_note(self.dragging_note)
                        self._select_slot(slot)
                        self._update_slot_labels()
                        break

                self.remove_widget(self.drag_label)
                self.drag_label = None
                self.dragging_note = None
            return True

        for slot in self.slots:
            if slot.collide_point(touch.x, touch.y):
                self._select_slot(slot)
                return True

        return super().on_touch_up(touch)

    def _select_slot(self, slot):
        if self.selected_slot:
            self.selected_slot.set_selected(False)
        self.selected_slot = slot
        slot.set_selected(True)

    def on_update(self):
        self.loop_engine.on_update()
