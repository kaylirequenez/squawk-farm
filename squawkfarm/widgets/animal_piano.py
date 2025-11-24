# squawkfarm/widgets/animal_piano.py

from kivy.uix.widget import Widget
from kivy.graphics import Rectangle, Color
from typing import List, Optional, Tuple


class AnimalPianoNote(Widget):
    """A single piano note rectangle with specified size and position."""
    
    def __init__(self, x: float, y: float, width: float, height: float,
                 color: Tuple[float, float, float, float], **kwargs):
        super(AnimalPianoNote, self).__init__(**kwargs)
        self.pos = (x, y)            # in WINDOW coords
        self.note_width = width
        self.note_height = height

        self.note_color = color
        self.original_color = color  # for unhighlighting
        self.is_selected = False

        self.rect: Rectangle | None = None

        self.size_hint = (None, None)
        self.size = (self.note_width, self.note_height)
        self._draw_note()
        
    def _draw_note(self):
        """Draw or redraw the rectangle with current size/color/pos."""
        self.canvas.clear()
        with self.canvas:
            Color(*self.note_color)
            self.rect = Rectangle(pos=self.pos, size=(self.note_width, self.note_height))
    
    def set_position(self, x: float, y: float):
        """Update the note position in pixels."""
        self.pos = (x, y)
        if self.rect:
            self.rect.pos = self.pos

    def set_size(self, width: float, height: float):
        """Update the note size in pixels."""
        self.note_width = width
        self.note_height = height
        self.size = (self.note_width, self.note_height)
        if self.rect:
            self.rect.size = self.size
    
    def set_color(self, color: Tuple[float, float, float, float]):
        """Change the color of the note."""
        self.note_color = color
        self.original_color = color
        self._draw_note()
    
    def set_selected(self, selected: bool):
        """Highlight or unhighlight the note by brightening the color."""
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
    """Container widget for managing multiple piano notes."""
    
    def __init__(self, **kwargs):
        super(AnimalPiano, self).__init__(**kwargs)
        self.notes: List[AnimalPianoNote] = []
        self.selected_note: Optional[AnimalPianoNote] = None
        self.note_colors = {
            "small":  (0.8, 0.6, 0.2, 1),
            "medium": (0.6, 0.8, 0.2, 1),
            "large":  (0.2, 0.6, 0.8, 1),
        }

        self.size_hint = (None, None)
        # Screen will set self.size / pos to cover the grid
    
    def add_note(self, x: float, y: float,
                 width: float, height: float,
                 size_type: str = "small") -> AnimalPianoNote:
        color = self.note_colors.get(size_type, self.note_colors["small"])
        note = AnimalPianoNote(x, y, width, height, color)
        self.notes.append(note)
        self.add_widget(note)
        return note
    
    def remove_note(self, note: AnimalPianoNote):
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

    def set_selected(self, note: Optional[AnimalPianoNote]):
        if self.selected_note and self.selected_note is not note:
            self.selected_note.set_selected(False)
        self.selected_note = note
        if note:
            note.set_selected(True)
    
    # def get_notes_at_position(self, x: float, y: float, tolerance: float = 10.0) -> List[AnimalPianoNote]:
    #     """Get all notes that intersect with the given position within tolerance.
        
    #     Args:
    #         x: X coordinate to check
    #         y: Y coordinate to check
    #         tolerance: Distance tolerance for intersection
            
    #     Returns:
    #         List of notes at the position
    #     """
    #     notes_at_pos = []
    #     for note in self.notes:
    #         nx, ny = note.pos
    #         w, h = note.size
    #         if (
    #             x >= nx - tolerance
    #             and x <= nx + w + tolerance
    #             and y >= ny - tolerance
    #             and y <= ny + h + tolerance
    #         ):
    #             notes_at_pos.append(note)
        
    #     return notes_at_pos
    
    # def get_notes_by_size(self, size_type: str) -> List[AnimalPianoNote]:
    #     """Get all notes of a specific size type."""
    #     return [note for note in self.notes if note.size_type == size_type]
    
    # def snap_to_grid(self, x: float, y: float) -> Tuple[float, float]:
    #     """Snap coordinates to the loop editor grid.
        
    #     Args:
    #         x: X coordinate to snap
    #         y: Y coordinate to snap
            
    #     Returns:
    #         Tuple of snapped (x, y) coordinates
    #     """
    #     # Calculate grid dimensions based on loop editor
    #     width = Window.width
    #     margin = width / 15
    #     draw_width = width - 2 * margin
    #     center_y = Window.height / 2
    #     line_spacing = Window.height * 0.05
        
    #     # Snap X to beat divisions (8 beats total)
    #     beat_width = draw_width / 8
    #     relative_x = x - margin
    #     snapped_beat = round(relative_x / beat_width)
    #     snapped_x = margin + (snapped_beat * beat_width)
        
    #     # Snap Y to horizontal line positions
    #     relative_y = y - (center_y - 3.5 * line_spacing)
    #     snapped_line = round(relative_y / line_spacing)
    #     snapped_y = center_y + (snapped_line - 3.5) * line_spacing
        
    #     return (snapped_x, snapped_y)
