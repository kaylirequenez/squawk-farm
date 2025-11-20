"""Melody composition generation."""

from __future__ import annotations

from typing import List
import random

from .utils import snap_to_scale


def generate_random_melody(
    engine,
    animal_id: str,
) -> None:
    """
    Generate a random melody pattern for a given animal and write it into the grid.

    This is a stub implementation that will be expanded to:
    - Generate melodic phrases using scale degrees
    - Create interesting rhythmic patterns
    - Use contour and direction for musical interest
    - Respect time signature and measure boundaries
    - Consider harmonic context from bass/harmony

    Parameters
    ----------
    engine : LoopEngine
        Global loop engine instance.
    animal_id : str
        Animal to generate melody for. Should have role "melody".
    """
    # TODO: Implement melody generation
    # For now, just clear the grid
    engine.clear_loops_from_grid(animal_id)
    
    # Future implementation will:
    # 1. Get scale notes based on key and mode
    # 2. Choose melodic contour (ascending, descending, arch, etc.)
    # 3. Generate rhythmic pattern with variation
    # 4. Select scale degrees for each note
    # 5. Use step-wise motion with occasional leaps
    # 6. Create phrases that respect measure boundaries
    pass
