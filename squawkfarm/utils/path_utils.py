"""Utility functions for constructing paths to project assets and data."""
import os

def _get_base_dir() -> str:
    """Return absolute path to project root (folder containing assets/, data/, etc.)."""
    return os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

def get_ui_asset_path(filename: str) -> str:
    """
    Get the absolute path to a UI asset in assets/ui_images/.
    """
    return os.path.join(_get_base_dir(), "assets", "ui_images", filename)

def get_recordings_dir() -> str:
    """
    Return the absolute path to the recordings directory: data/recordings/.
    """
    return os.path.join(_get_base_dir(), "data", "recordings")

def get_recording_wav_path(animal_id: str) -> str:
    """
    Get the absolute path to the .wav file for a given animal_id.
    """
    return os.path.join(get_recordings_dir(), animal_id + ".wav")

def get_animal_data_dir(animal_id: str) -> str:
    """
    Return the path to data/animals/<animal_id>.
    """
    return os.path.join(_get_base_dir(), "data", "animals", animal_id)