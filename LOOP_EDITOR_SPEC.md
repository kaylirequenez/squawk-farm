# Loop Editor Screen Integration Spec

This document outlines the integration requirements for the loop editor screen to work with the composition generation system.

## Overview

The loop editor screen allows users to:
1. View and edit an animal's loop instances on the grid
2. Manually drag/move loop instances (left/right for timing, up/down for pitch)
3. Change the animal's role (bass, harmony, melody, percussion)
4. Generate new random patterns for the current role
5. See the appropriate MIDI range for the animal's role

## Required Imports

```python
from squawkfarm.services.composition import (
    generate_random_baseline,
    generate_random_harmony,
    generate_random_melody,
    generate_random_percussion,
)
from squawkfarm.services.composition.utils import get_role_register
```

## Integration Points

### 1. On Screen Enter - Display Correct MIDI Range

When entering the loop editor for an animal, show the appropriate MIDI note range based on the animal's role.

```python
def on_enter(self):
    # ... existing setup code ...
    
    # Get the animal's current role
    animal_loop = self.loop_engine.loops.get(self.animal_id)
    role = self.loop_engine.get_role(self.animal_id)  # "bass", "harmony", "melody", or "percussion"
    
    # Get the MIDI range for this role
    low_midi, high_midi = get_role_register(role)
    
    # Use low_midi and high_midi to:
    # - Display note labels on the UI (e.g., C2 to E3 for bass)
    # - Constrain pitch editing to this range
    # - Show visual guides for the role's register
    
    # Note: MIDI numbers can be converted to note names:
    # MIDI 48 = C3, MIDI 60 = C4, MIDI 72 = C5, etc.
```

**Role Registers:**
- Bass: 36-52 (C2 to E3)
- Harmony: 48-72 (C3 to C5)
- Melody: 60-84 (C4 to C6)
- Percussion: No specific range (use animal's natural pitch)

### 2. Generate New Pattern Button

Add a button (e.g., "Regenerate Pattern" or "New Pattern") that generates a fresh random pattern for the current role.

```python
def _on_regenerate_pattern(self, *_):
    """
    Generate a new random pattern for this animal based on its current role.
    This replaces all existing loop instances with a new generated pattern.
    """
    animal_loop = self.loop_engine.loops.get(self.animal_id)
    role = animal_loop.role
    
    # Call the appropriate generation function based on role
    # NOTE: right now only first implemented
    if role == "bass":
        generate_random_baseline(self.loop_engine, self.animal_id)
    elif role == "harmony":
        generate_random_harmony(self.loop_engine, self.animal_id)
    elif role == "melody":
        generate_random_melody(self.loop_engine, self.animal_id)
    elif role == "percussion":
        generate_random_percussion(self.loop_engine, self.animal_id)
    
    # Refresh the UI to show the new pattern
    self._refresh_grid_display()
```

### 3. Change Role Dropdown/Buttons

Add UI to change the animal's role. When the role changes:
1. Update the role in the loop engine
2. Generate a new pattern appropriate for the new role
3. Update the MIDI range display

```python
def _on_role_change(self, new_role):
    """
    Change the animal's role and generate an appropriate pattern.
    
    :param new_role: One of "bass", "harmony", "melody", "percussion"
    """
    # Update the role in the loop engine
    self.loop_engine.set_role_of_loop(self.animal_id, new_role)
    
    # Get the new MIDI range for this role
    low_midi, high_midi = get_role_register(new_role)
    
    # Update UI to show new range
    self._update_midi_range_display(low_midi, high_midi)
    
    # Generate a pattern appropriate for the new role
    if new_role == "bass":
        generate_random_baseline(self.loop_engine, self.animal_id)
    elif new_role == "harmony":
        generate_random_harmony(self.loop_engine, self.animal_id)
    elif new_role == "melody":
        generate_random_melody(self.loop_engine, self.animal_id)
    elif new_role == "percussion":
        generate_random_percussion(self.loop_engine, self.animal_id)
    
    # Refresh the grid to show the new pattern
    self._refresh_grid_display()
```

**UI Suggestion:** 
- Use a Spinner dropdown with options: ["Bass", "Harmony", "Melody", "Percussion"]
- Or use 4 toggle buttons to switch between roles

### 4. Manual Editing: Drag Loop Instances

Allow users to drag loop instances on the grid to change their timing (horizontal) or pitch (vertical).

#### Horizontal Dragging (Change Timing)

```python
def on_touch_move(self, touch):
    """Handle dragging a loop instance horizontally to change its start time."""
    if self.dragging_loop_instance:
        # Calculate new slot position from touch.x
        new_start_slot = self.grid.get_slot_from_x(touch.x)
        
        # Slide the loop instance to the new position
        # The overlap parameter controls whether instances can overlap
        # Set to False to prevent overlapping (will keep at old position if collision)
        # Set to True to allow overlapping
        final_slot = self.loop_engine.slide_loop_instance(
            animal_id=self.animal_id,
            old_start_slot=self.old_start_slot,
            new_start_slot=new_start_slot,
            overlap=False  # Change to True if you want to allow overlapping
        )
        
        # Update visual position (final_slot may differ from new_start_slot if collision occurred)
        self._update_loop_instance_visual(final_slot)
        
        return True
```

**Note:** `slide_loop_instance` returns the actual final position. If `overlap=False` and there's a collision, it returns the original position unchanged.

#### Vertical Dragging (Change Pitch)

```python
def on_touch_move(self, touch):
    """Handle dragging a loop instance vertically to change its pitch."""
    if self.dragging_loop_instance:
        # Calculate new MIDI note from touch.y
        new_midi = self.grid.get_midi_from_y(touch.y)
        
        # Get the role's MIDI range to constrain the pitch
        role = self.loop_engine.loops[self.animal_id].role
        low_midi, high_midi = get_role_register(role)
        
        # Clamp to role's register
        new_midi = max(low_midi, min(high_midi, new_midi))
        
        # Update the pitch of this loop instance
        self.loop_engine.set_pitch_of_loop_instance(
            animal_id=self.animal_id,
            start_slot=self.dragging_start_slot,
            midi=new_midi
        )
        
        # Update visual position
        self._update_loop_instance_visual(self.dragging_start_slot, new_midi)
        
        return True
```

#### Combined 2D Dragging

For a smoother UX, you can allow both horizontal and vertical dragging simultaneously:

```python
def on_touch_down(self, touch):
    """Detect if user clicked on a loop instance to start dragging."""
    # Check if touch is over a loop instance
    loop_info = self.loop_engine.get_loop_instance_info(self.animal_id)
    
    for start_slot, num_slots, midi in loop_info:
        if self._is_touch_over_instance(touch, start_slot, num_slots, midi):
            self.dragging_loop_instance = True
            self.dragging_start_slot = start_slot
            self.original_midi = midi
            touch.grab(self)
            return True
    
    return super().on_touch_down(touch)

def on_touch_move(self, touch):
    """Handle 2D dragging: horizontal for timing, vertical for pitch."""
    if self.dragging_loop_instance and touch.grab_current == self:
        # HORIZONTAL: Change timing
        new_start_slot = self.grid.get_slot_from_x(touch.x)
        
        # If slot changed, slide the instance
        if new_start_slot != self.dragging_start_slot:
            final_slot = self.loop_engine.slide_loop_instance(
                animal_id=self.animal_id,
                old_start_slot=self.dragging_start_slot,
                new_start_slot=new_start_slot,
                overlap=False  # Set True to allow overlapping
            )
            self.dragging_start_slot = final_slot
        
        # VERTICAL: Change pitch
        new_midi = self.grid.get_midi_from_y(touch.y)
        
        # Constrain to role's register
        role = self.loop_engine.loops[self.animal_id].role
        low_midi, high_midi = get_role_register(role)
        new_midi = max(low_midi, min(high_midi, new_midi))
        
        # Update pitch if changed
        if new_midi != self.original_midi:
            self.loop_engine.set_pitch_of_loop_instance(
                animal_id=self.animal_id,
                start_slot=self.dragging_start_slot,
                midi=new_midi
            )
            self.original_midi = new_midi
        
        # Update visual
        self._update_loop_instance_visual(self.dragging_start_slot, new_midi)
        
        return True
    
    return super().on_touch_move(touch)

def on_touch_up(self, touch):
    """End dragging."""
    if self.dragging_loop_instance and touch.grab_current == self:
        touch.ungrab(self)
        self.dragging_loop_instance = False
        self.dragging_start_slot = None
        self.original_midi = None
        return True
    
    return super().on_touch_up(touch)
```

### 5. Helper: Refresh Grid Display

You'll need a method to update the UI after generating new patterns:

```python
def _refresh_grid_display(self):
    """
    Refresh the grid display to show updated loop instances.
    Called after generating new patterns or changing roles.
    """
    # Get the updated loop instance info
    loop_info = self.loop_engine.get_loop_instance_info(self.animal_id)
    # loop_info is a list of (start_slot, num_slots, midi) tuples
    
    # Clear existing visual elements for this animal
    # ... your existing grid clearing code ...
    
    # Redraw loop instances on the grid
    for start_slot, num_slots, midi in loop_info:
        # Draw this loop instance on the grid
        # - Position: start_slot to (start_slot + num_slots)
        # - Pitch: midi (use this to determine vertical position)
        pass
```

### 6. Helper: MIDI to Note Name Conversion

If you want to display note names (like "C3", "G4") instead of MIDI numbers:

```python
def midi_to_note_name(midi: int) -> str:
    """Convert MIDI number to note name (e.g., 60 -> 'C4')."""
    notes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    octave = (midi // 12) - 1
    note = notes[midi % 12]
    return f"{note}{octave}"
```

## Example UI Layout

```
┌─────────────────────────────────────────────────────────┐
│  Animal: Chicken #123                Role: [Bass ▼]      │
│  Range: C2 - E3                      [New Pattern]       │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  E3  ─────────────────────────────────────────────       │
│  D3  ──■■■──────■■■──────■■■──────■■■────────────       │
│  C3  ─────────────────────────────────────────────       │
│  B2  ─────────────────────────────────────────────       │
│  A2  ─────────────────────────────────────────────       │
│  G2  ──────────────────────────■■■────────────────       │
│  F2  ─────────────────────────────────────────────       │
│  E2  ─────────────────────────────────────────────       │
│  D2  ─────────────────────────────────────────────       │
│  C2  ■■■────────────────────────────────■■■───────       │
│                                                           │
│      | Measure 1 | Measure 2 | Measure 3 | Measure 4|   │
└─────────────────────────────────────────────────────────┘
```

## State Management

The loop editor needs to track:
- `self.animal_id`: The animal being edited
- `self.current_role`: The animal's current role (from `loop_engine.loops[animal_id].role`)
- MIDI range bounds: `(low_midi, high_midi)` from `get_role_register(role)`

## Testing Checklist

- [ ] Entering loop editor shows correct MIDI range for animal's role
- [ ] "New Pattern" button generates appropriate pattern for current role
- [ ] Changing role updates MIDI range display
- [ ] Changing role generates appropriate pattern for new role
- [ ] Bass role shows patterns using root and fifth
- [ ] Harmony role shows patterns (when implemented)
- [ ] Melody role shows patterns (when implemented)
- [ ] Percussion role shows patterns (when implemented)
- [ ] Grid correctly displays loop instances after generation
- [ ] Multiple regenerations work without errors
- [ ] Can drag loop instances horizontally to change timing
- [ ] Horizontal dragging respects collision detection when overlap=False
- [ ] Can drag loop instances vertically to change pitch
- [ ] Vertical dragging is constrained to role's MIDI range
- [ ] 2D dragging (timing + pitch) works smoothly
- [ ] Dragged instances play back at new positions/pitches correctly

## Notes

- **Harmony and Melody**: Currently stub implementations that just clear the grid. They will be implemented later with similar logic to bass generation.
- **Percussion**: Also a stub. Will focus on rhythmic patterns rather than pitched notes.
- **Manual Editing**: The generation functions are meant to give users a starting point. Users can still manually edit, add, or remove loop instances after generation.
- **Key/Mode Awareness**: All generation functions respect the current key (root MIDI) and mode (major/minor) from `loop_engine.get_root()` and `loop_engine.get_key_mode()`.
- **Overlap Control**: The `overlap` parameter in `slide_loop_instance()` controls whether instances can overlap:
  - `overlap=False` (recommended): Prevents overlapping, returns original position if collision detected
  - `overlap=True`: Allows instances to stack on top of each other (may cause audio issues)
- **Pitch Constraints**: Always constrain pitch changes to the role's register using `get_role_register()` to maintain musical coherence

## Questions?

If you need clarification on:
- How to get animal info: `loop_engine.loops.get(animal_id)` returns a `Loop` object with `.role`, `.midi`, `.volume`, etc.
- How to get loop instances: `loop_engine.get_loop_instance_info(animal_id)` returns list of `(start_slot, num_slots, midi)`
- How slots work: See `loop_engine.py` for slot/frame/time conversion utilities
