"""Utility functions for constructing paths to project assets and data."""
import os

def _get_base_dir():
    """Return absolute path to project root (folder containing assets/, data/, etc.)."""
    return os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

def get_ui_asset_path(filename):
    """
    Get the absolute path to a UI asset in assets/ui_images/.
    """
    return os.path.join(_get_base_dir(), "assets", "ui_images", filename)

def get_recordings_dir():
    """
    Return the absolute path to the recordings directory: data/recordings/.
    """
    return os.path.join(_get_base_dir(), "data", "recordings")

def get_animal_recording_dir(animal_id):
    """
    Return the path to data/recordings/<animal_id>/.
    Creates the directory if it doesn't exist.
    """
    path = os.path.join(get_recordings_dir(), animal_id)
    os.makedirs(path, exist_ok=True)
    return path

def get_recording_wav_path(animal_id, recording_type):
    """
    Get the absolute path to the .wav file for a given animal_id and recording type.
    Recording type can be "raw" or "tuned".
    """
    return os.path.join(get_animal_recording_dir(animal_id), recording_type + ".wav")

def get_animal_data_dir(animal_id):
    """
    Return the path to data/animals/<animal_id>.
    Creates the directory if it doesn't exist.
    """
    path = os.path.join(_get_base_dir(), "data", "animals", animal_id)
    os.makedirs(path, exist_ok=True)
    return path

def get_metronome_sound_path():
    """
    Get the absolute path to the metronome sound file.
    """
    return os.path.join(_get_base_dir(), "squawkfarm", "Defualt_sounds", "Metronome.wav")