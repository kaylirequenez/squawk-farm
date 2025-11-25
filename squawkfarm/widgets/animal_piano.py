from kivy.uix.widget import Widget
from kivy.graphics import Rectangle, Color

class AnimalPianoNote(Widget):
    def __init__(self, x, y, width, height, color, **kwargs):
        super(AnimalPianoNote, self).__init__(**kwargs)
        self.pos = (x, y)
        self.note_width = width
        self.note_height = height

        self.note_color = color
        self.original_color = color
        self.is_selected = False

        self.rect = None
        self.shadow_rect = None

        self.size_hint = (None, None)
        self.size = (self.note_width, self.note_height)
        self._draw_note()

    def _draw_note(self):
        self.canvas.clear()
        with self.canvas:
            Color(0.15, 0.1, 0.05, 0.7)
            self.shadow_rect = Rectangle(
                pos=(self.pos[0] + 5, self.pos[1] - 5),
                size=(self.note_width, self.note_height)
            )
            Color(*self.note_color)
            self.rect = Rectangle(pos=self.pos, size=(self.note_width, self.note_height))
    
    def set_position(self, x, y):
        self.pos = (x, y)
        if self.rect:
            self.rect.pos = self.pos
        if self.shadow_rect:
            self.shadow_rect.pos = (x + 5, y - 5)

    def set_size(self, width, height):
        self.note_width = width
        self.note_height = height
        self.size = (self.note_width, self.note_height)
        if self.rect:
            self.rect.size = self.size
    
    def set_color(self, color):
        self.note_color = color
        self.original_color = color
        self._draw_note()
    
    def set_selected(self, selected):
        self.is_selected = selected
        if selected:
            r, g, b, a = self.original_color
            self.note_color = (min(1.0, r + 0.3),
                               min(1.0, g + 0.3),
                               min(1.0, b + 0.3),
                               a)
        else:
            self.note_color = self.original_color
        self._draw_note()


class AnimalPiano(Widget):
    def __init__(self, **kwargs):
        super(AnimalPiano, self).__init__(**kwargs)
        self.notes = []
        self.selected_note = None
        self.note_colors = {
            "small":  (1.0, 0.95, 0.7, 1),
            "medium": (1.0, 0.95, 0.7, 1),
            "large":  (1.0, 0.95, 0.7, 1),
        }

        self.size_hint = (None, None)
        # Screen will set self.size / pos to cover the grid
    
    def add_note(self, x, y, width, height, size_type="small"):
        color = self.note_colors.get(size_type, self.note_colors["small"])
        note = AnimalPianoNote(x, y, width, height, color)
        self.notes.append(note)
        self.add_widget(note)
        return note
    
    def remove_note(self, note):
        if note in self.notes:
            if self.selected_note is note:
                self.selected_note = None
            self.notes.remove(note)
            self.remove_widget(note)
    
    def clear_notes(self):
        for n in self.notes:
            self.remove_widget(n)
        self.notes.clear()
        self.selected_note = None

    def set_selected(self, note):
        if self.selected_note and self.selected_note is not note:
            self.selected_note.set_selected(False)
        self.selected_note = note
        if note:
            note.set_selected(True)
