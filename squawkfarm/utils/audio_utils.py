"""Audio utilities: loading, saving, normalization helpers."""
import numpy as np
import librosa
from imslib.audio import Audio
from imslib.writer import write_wave_file
from imslib.wavegen import convert_channels
from squawkfarm.utils.path_utils import get_recording_wav_path


def ensure_mono_audio(audio_data, num_channels):
    """
    Convert audio data to mono if it's stereo.
    Uses the existing convert_channels function from imslib.wavegen.
    
    :param audio_data: Numpy array of audio data (interleaved if stereo).
    :param num_channels: Number of channels in the audio data.
    :returns: Mono audio data as numpy array.
    """
    if num_channels == 1:
        return audio_data
    elif num_channels == 2:
        # Convert stereo to mono by averaging channels
        return convert_channels(audio_data, 2, 1)
    else:
        # For other channel counts, average all channels
        return convert_channels(audio_data, num_channels, 1)


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


def tune_sample_and_save(animal_id, data, num_channels=1):
    """
    Detect pitch, tune to the nearest semitone, and save as tuned.wav.
    
    :param animal_id: The animal's unique identifier.
    :param data: Audio data as numpy array (may be stereo).
    :param num_channels: Number of channels in the audio data (default 1 for mono).
    :returns: Tuple of (tuned_audio_data, detected_midi_note).
    """
    # Convert to mono if stereo
    if num_channels != 1:
        data = ensure_mono_audio(data, num_channels)
    
    # Detect pitch and tune to nearest semitone
    f0 = _estimate_f0_median(data, Audio.sample_rate)
    if f0 > 0:
        src_midi = librosa.hz_to_midi(f0)
        target_midi = round(src_midi)  # Round to nearest semitone
        n_steps = target_midi - src_midi
        y_tuned = librosa.effects.pitch_shift(data, sr=Audio.sample_rate, n_steps=n_steps)
        
        y_tuned = fade_in_out(y_tuned, fade_duration_ms=10)
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

def time_to_frame(time_sec):
    return int(time_sec * Audio.sample_rate)

def frame_to_time(frame):
    return frame / float(Audio.sample_rate)

def fade_in_out(data, fade_duration_ms=10):
    """
    Apply fade-in and fade-out to audio data.
    
    :param data: Audio data as numpy array.
    :param fade_duration_ms: Duration of fade in milliseconds.
    :returns: Audio data with fade applied.
    """
    fade_samples = int(Audio.sample_rate * fade_duration_ms / 1000)

    fade_window = np.hanning(fade_samples * 2)[:fade_samples]

    data[:fade_samples] = data[:fade_samples] * fade_window
    
    fade_out_window = np.hanning(fade_samples * 2)[fade_samples:]

    data[-fade_samples:] = data[-fade_samples:] * fade_out_window

    return data