"""Audio utilities: loading, saving, normalization helpers."""
import numpy as np
import librosa
from imslib.audio import Audio
from imslib.writer import write_wave_file
from squawkfarm.utils.path_utils import get_recording_wav_path

def _estimate_f0_median(y, sr):
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


def tune_sample_and_save(animal_id, data):
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


def tune_to_midi(data, base_midi, target_midi):
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


