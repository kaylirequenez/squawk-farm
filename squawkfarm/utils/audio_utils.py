"""Audio utilities: loading, saving, normalization helpers."""
import numpy as np
import librosa
from imslib.audio import Audio
from imslib.writer import write_wave_file
from squawkfarm.utils.path_utils import get_recording_wav_path

def frame_to_time(frame: int) -> float:
    """Convert frame index to time in seconds."""
    return frame / Audio.sample_rate

def time_to_frame(time: float) -> int:
    """Convert time in seconds to frame index."""
    return int(time * Audio.sample_rate)


def _estimate_f0_median(y: np.ndarray, sr: int) -> float:
    """Estimate the median fundamental frequency of voiced audio."""
    f0 = librosa.yin(
        y,
        fmin=librosa.note_to_hz("C2"),
        fmax=librosa.note_to_hz("C7"),
    )
    voiced = f0 > 0
    if not np.any(voiced):
        return 0.0
    return float(np.median(f0[voiced]))


def tune_sample_and_save(animal_id: str, data: np.ndarray) -> tuple[np.ndarray, int]:
    """
    Detect pitch, tune to the nearest semitone, and save as tuned.wav.
    
    :param animal_id: The animal's unique identifier.
    :param data: Audio data as numpy array.
    :returns: Tuple of (tuned_audio_data, detected_midi_note).
    """
    # Detect pitch and tune to nearest semitone
    f0 = _estimate_f0_median(data, Audio.sample_rate)
    if f0 > 0:
        src_midi = librosa.hz_to_midi(f0)
        target_midi = round(src_midi)  # Round to nearest semitone
        n_steps = target_midi - src_midi
        y_tuned = librosa.effects.pitch_shift(data, sr=Audio.sample_rate, n_steps=n_steps)
    else:
        # No pitch detected, use original and default to middle C
        # TODO: ask them to re-record
        raise ValueError("No pitch detected")
    
    # Save tuned audio
    tuned_path = get_recording_wav_path(animal_id, "tuned")
    write_wave_file(y_tuned, 1, tuned_path)
    
    return y_tuned, int(target_midi)


def tune_to_midi(data: np.ndarray, base_midi: int, target_midi: int) -> np.ndarray:
    """
    Tune audio data from one MIDI note to another.
    
    :param data: Audio data as numpy array.
    :param base_midi: The current MIDI note of the input audio.
    :param target_midi: The target MIDI note to tune to.
    :returns: Pitch-shifted audio data.
    """
    semitones = target_midi - base_midi
    
    if semitones == 0:
        y_shifted = data
    else:
        y_shifted = librosa.effects.pitch_shift(data, sr=Audio.sample_rate, n_steps=semitones)
    
    return y_shifted


def guess_role_from_pitch(animal_midi: int, root_midi: int = 60) -> str:
    """
    Guess the role of an animal based on its pitch relative to the root note.
    
    :param animal_midi: The MIDI note of the animal's audio.
    :param root_midi: The root MIDI note of the key (default: C4 = 60).
    :returns: "bass", "harmony", or "melody".
    """
    offset = animal_midi - root_midi  # in semitones

    if offset <= -5:    # more than a fourth below root
        return "bass"
    elif offset >= 7:   # a fifth or more above root
        return "melody"
    else:
        return "harmony"


def guess_initial_role(
    animal_midi: int,
    root_midi: int = 60,
    beats: int = 4,
) -> str:
    """
    Guess an initial role for an animal using both pitch and loop length.

    Rules:
    - If the loop is very short (1 beat), we *assume* it is likely percussive
      or a short stab, and default to "percussion".
    - Otherwise, we use pitch-based guessing to choose between
      "bass", "harmony", and "melody".
    """
    # Treat 1-beat (or less if changed in future) samples as likely percussion by default.
    if beats <= 1:
        return "percussion"

    # For 2 or 4 beats, fall back to pitch-based roles.
    return guess_role_from_pitch(animal_midi, root_midi)


