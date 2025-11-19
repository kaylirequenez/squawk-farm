"""Composition generation package."""

from .bass import generate_random_baseline
from .harmony import generate_random_harmony
from .melody import generate_random_melody
from .percussion import generate_random_percussion

__all__ = [
    "generate_random_baseline",
    "generate_random_harmony",
    "generate_random_melody",
    "generate_random_percussion",
]
