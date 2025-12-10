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
    return os.path.join(_get_base_dir(), get_default_sounds_dir(), "Metronome.wav")


def get_default_sounds_dir():
    """
    Return the path to the default sounds directory: squawkfarm/Defualt_sounds/.
    """
    return os.path.join(_get_base_dir(), "squawkfarm", "Defualt_sounds")


def get_default_sound_path(sound_name):
    """
    Get the absolute path to a default sound file by name (without extension).
    Sound name should be like "bass" which maps to "bass.wav".
    """
    default_sounds_dir = get_default_sounds_dir()
    # Try common audio extensions
    for ext in [".wav", ".mp3", ".m4a"]:
        path = os.path.join(default_sounds_dir, sound_name + ext)
        if os.path.exists(path):
            return path
    # If not found, default to .wav
    return os.path.join(default_sounds_dir, sound_name + ".wav")


def get_available_default_sounds():
    """
    Get a list of available default sounds (excluding Metronome.wav and non-WAV files).
    Returns a list of sound names.
    Only includes .wav files since the audio system requires WAV format.
    """
    default_sounds_dir = get_default_sounds_dir()
    sound_files = []

    if not os.path.exists(default_sounds_dir):
        return sound_files

    for filename in sorted(os.listdir(default_sounds_dir)):
        # Skip non-WAV files, non-audio files, and the metronome
        if filename.lower() == "metronome.wav" or filename.startswith("."):
            continue
        if filename.lower().endswith(".wav"):
            # Convert filename to display name (bass.wav -> "bass")
            display_name = os.path.splitext(filename)[0]
            sound_files.append(display_name)

    return sound_files
