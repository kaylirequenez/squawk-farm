# squawkfarm/services/arpeggio_processor.py

import os
from typing import Sequence

import numpy as np
import librosa
import soundfile as sf

from squawkfarm.services.loop_engine import LoopEngine


C_MAJOR_ARP = [0, 4, 7, 12] 


def _estimate_f0_median(y: np.ndarray, sr: int) -> float:
    try:
        f0 = librosa.yin(
            y,
            fmin=librosa.note_to_hz("C2"),
            fmax=librosa.note_to_hz("C7"),
        )
        voiced = f0 > 0
        if not np.any(voiced):
            return 0.0
        return float(np.median(f0[voiced]))
    except Exception as e:
        print(f"Warning: F0 estimation failed: {e}")
        return 0.0  # Fallback to no pitch correction


def build_arpeggiated_loop_for_animal(
    loop_engine: LoopEngine,
    animal_id: str,
    recording_path: str,
    out_dir: str | None = None,
    semitone_pattern: Sequence[int] = C_MAJOR_ARP,
    target_midi: int = 60, 
) -> str:
    if out_dir is None:
        out_dir = os.path.dirname(recording_path) or "."

    try:
        y, sr = librosa.load(recording_path, sr=None, mono=True)
    except Exception as e:
        print(f"Error loading audio file {recording_path}: {e}")
        # Fallback: just add the original recording without arpeggio processing
        loop_engine.add_or_update_animal_loop(animal_id, recording_path)
        loop_engine.add_loop_to_grid(animal_id, [0])
        return recording_path

    # Pitch correction with error handling
    try:
        f0 = _estimate_f0_median(y, sr)
        if f0 > 0:
            src_midi = librosa.hz_to_midi(f0)
            n_steps_to_target = target_midi - src_midi
            y_tuned = librosa.effects.pitch_shift(y, sr=sr, n_steps=n_steps_to_target)
        else:
            y_tuned = y
    except Exception as e:
        print(f"Warning: Pitch correction failed: {e}, using original audio")
        y_tuned = y

    # Arpeggio generation with error handling
    segments: list[np.ndarray] = []
    for semitones in semitone_pattern:
        try:
            if semitones == 0:
                segments.append(y_tuned)
            else:
                shifted = librosa.effects.pitch_shift(y_tuned, sr=sr, n_steps=semitones)
                segments.append(shifted)
        except Exception as e:
            print(f"Warning: Pitch shift failed for {semitones} semitones: {e}, using original segment")
            segments.append(y_tuned)  # Fallback to original

    try:
        arpeggio = np.concatenate(segments)
        out_path = os.path.join(out_dir, f"{animal_id}_arpeggio_autotuned.wav")
        sf.write(out_path, arpeggio, sr)
    except Exception as e:
        print(f"Error creating arpeggio file: {e}, using original recording")
        out_path = recording_path

    try:
        loop_engine.add_or_update_animal_loop(animal_id, out_path)
        loop_engine.add_loop_to_grid(animal_id, [0])
    except Exception as e:
        print(f"Error adding loop to engine: {e}")
        # Don't re-raise, just log the error

    return out_path
