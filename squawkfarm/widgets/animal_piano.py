"""Animal Piano widget for creating MIDI note-like rectangles.

This widget creates rectangular notes similar to those in a DAW piano roll,
with consistent height matching the spacing between horizontal lines in the 
loop editor screen, and variable lengths based on beat sizes.
"""

from kivy.uix.widget import Widget
from kivy.graphics import Rectangle, Color
from kivy.core.window import Window
from typing import List, Tuple, Dict


class AnimalPianoNote(Widget):
    """A single piano note rectangle with specified size and position."""
    
    def __init__(self, size_type="small", color=(0.8, 0.6, 0.2, 1), **kwargs):
        super(AnimalPianoNote, self).__init__(**kwargs)
        
        # Size types and their beat multipliers
        self.size_multipliers = {
            "small": 1,    # 1 beat
            "medium": 2,   # 2 beats  
            "large": 4     # 4 beats
        }
        
        self.size_type = size_type
        self.note_color = color
        self.rect = None
        
        # Calculate dimensions based on loop editor spacing
        self._update_dimensions()
        
        # Bind to window resize to update dimensions
        Window.bind(size=self._on_window_resize)
    
    def _update_dimensions(self):
        """Calculate note dimensions based on loop editor screen spacing."""
        # Height matches spacing between horizontal lines in loop editor
        self.note_height = Window.height * 0.05  # Same as line_spacing in loop editor
        
        # Width based on beat size - one beat is 1/8 of the draw area
        width = Window.width
        margin = width / 15
        draw_width = width - 2 * margin
        one_beat_width = draw_width / 8  # 8 beats total in loop editor
        
        multiplier = self.size_multipliers.get(self.size_type, 1)
        self.note_width = one_beat_width * multiplier
        
        # Update widget size
        self.size = (self.note_width, self.note_height)
        
        # Redraw the rectangle
        self._draw_note()
    
    def _draw_note(self):
        """Draw the note rectangle."""
        self.canvas.clear()
        
        with self.canvas:
            Color(*self.note_color)
            self.rect = Rectangle(pos=self.pos, size=(self.note_width, self.note_height))
    
    def set_position(self, x: float, y: float):
        """Set the position of the note and update the rectangle."""
        self.pos = (x, y)
        if self.rect:
            self.rect.pos = self.pos
    
    def _on_window_resize(self, window, width, height):
        """Handle window resize by updating dimensions."""
        self._update_dimensions()
    
    def set_size_type(self, size_type: str):
        """Change the size type of the note."""
        if size_type in self.size_multipliers:
            self.size_type = size_type
            self._update_dimensions()
    
    def set_color(self, color: Tuple[float, float, float, float]):
        """Change the color of the note."""
        self.note_color = color
        self._draw_note()


class AnimalPiano(Widget):
    """Container widget for managing multiple piano notes."""
    
    def __init__(self, **kwargs):
        super(AnimalPiano, self).__init__(**kwargs)
        self.notes: List[AnimalPianoNote] = []
        self.note_colors = {
            "small": (0.8, 0.6, 0.2, 1),    # Orange for small notes
            "medium": (0.6, 0.8, 0.2, 1),   # Green for medium notes  
            "large": (0.2, 0.6, 0.8, 1)     # Blue for large notes
        }
    
    def add_note(self, x: float, y: float, size_type: str = "small", 
                 color: Tuple[float, float, float, float] = None) -> AnimalPianoNote:
        """Add a new note to the piano roll at the specified position.
        
        Args:
            x: X position for the note
            y: Y position for the note  
            size_type: "small", "medium", or "large"
            color: RGBA color tuple, defaults to size-based color
            
        Returns:
            The created AnimalPianoNote instance
        """
        if color is None:
            color = self.note_colors.get(size_type, self.note_colors["small"])
        
        note = AnimalPianoNote(size_type=size_type, color=color)
        note.set_position(x, y)
        
        self.notes.append(note)
        self.add_widget(note)
        
        return note
    
    def remove_note(self, note: AnimalPianoNote):
        """Remove a note from the piano roll."""
        if note in self.notes:
            self.notes.remove(note)
            self.remove_widget(note)
    
    def clear_notes(self):
        """Remove all notes from the piano roll."""
        for note in self.notes:
            self.remove_widget(note)
        self.notes.clear()
    
    def get_notes_at_position(self, x: float, y: float, tolerance: float = 10.0) -> List[AnimalPianoNote]:
        """Get all notes that intersect with the given position within tolerance.
        
        Args:
            x: X coordinate to check
            y: Y coordinate to check
            tolerance: Distance tolerance for intersection
            
        Returns:
            List of notes at the position
        """
        notes_at_pos = []
        for note in self.notes:
            note_x, note_y = note.pos
            if (abs(x - note_x) <= tolerance + note.note_width and 
                abs(y - note_y) <= tolerance + note.note_height):
                notes_at_pos.append(note)
        
        return notes_at_pos
    
    def get_notes_by_size(self, size_type: str) -> List[AnimalPianoNote]:
        """Get all notes of a specific size type."""
        return [note for note in self.notes if note.size_type == size_type]
    
    def snap_to_grid(self, x: float, y: float) -> Tuple[float, float]:
        """Snap coordinates to the loop editor grid.
        
        Args:
            x: X coordinate to snap
            y: Y coordinate to snap
            
        Returns:
            Tuple of snapped (x, y) coordinates
        """
        # Calculate grid dimensions based on loop editor
        width = Window.width
        margin = width / 15
        draw_width = width - 2 * margin
        center_y = Window.height / 2
        line_spacing = Window.height * 0.05
        
        # Snap X to beat divisions (8 beats total)
        beat_width = draw_width / 8
        relative_x = x - margin
        snapped_beat = round(relative_x / beat_width)
        snapped_x = margin + (snapped_beat * beat_width)
        
        # Snap Y to horizontal line positions
        relative_y = y - (center_y - 3.5 * line_spacing)
        snapped_line = round(relative_y / line_spacing)
        snapped_y = center_y + (snapped_line - 3.5) * line_spacing
        
        return (snapped_x, snapped_y)
