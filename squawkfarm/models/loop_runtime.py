from typing import Dict, List, Optional, Tuple, Callable
import numpy as np

from imslib.wavegen import WaveGenerator
from imslib.wavesrc import WaveBuffer, WaveFile

from squawkfarm.models.loop import LoopInstance
from squawkfarm.utils import tune_to_midi

class RuntimeLoopInstance(object):
    """
    Runtime per-loop-instance data with audio buffer and muting information.
    """
    def __init__(self, data: np.ndarray, midi: int, muted_ranges: list[tuple[int, int]] = []):
        super(RuntimeLoopInstance, self).__init__()
        self.muted_ranges = muted_ranges if muted_ranges else []
        self.set_buffer(data, midi)

    def set_buffer(self, data: np.ndarray, midi: int) -> None:
        self.clean_data = data.copy()
        self.data = data.copy()
        self.midi = midi
        self.num_frames = len(self.data)
        self.num_channels = 1

        for start_frame, end_frame in self.muted_ranges:
            self.data[start_frame:end_frame] = 0
        
    def get_frames(self, start_frame: int, num_frames: int) -> np.ndarray:
        return self.data[start_frame:start_frame + num_frames]
    
    def get_num_channels(self) -> int:
        return self.num_channels

    def toggle_mute(self, start_frame: int, end_frame: int, mute: bool) -> None:
        start_frame = max(0, start_frame)
        end_frame = min(self.num_frames, end_frame)

        if mute:
            self.data[start_frame:end_frame] = 0
            # Add and merge overlapping ranges
            self._add_muted_range(start_frame, end_frame)
        else:
            self.data[start_frame:end_frame] = self.clean_data[start_frame:end_frame]
            # Remove the range
            self._remove_muted_range(start_frame, end_frame)

    def _add_muted_range(self, start_frame: int, end_frame: int) -> None:
        i, overlap = 0, False
        while not overlap and i < len(self.muted_ranges):
            existing_start, existing_end = self.muted_ranges[i]
            if existing_start <= start_frame <= existing_end:
                j = i + 1
                while j < len(self.muted_ranges) and end_frame >= self.muted_ranges[j][0]:
                    j += 1
                # Merge all overlapping ranges from i to j-1
                end_frame = max(end_frame, self.muted_ranges[j - 1][1])
                self.muted_ranges[i:j] = [(existing_start, end_frame)]
                overlap = True
            else:
                i += 1

        if not overlap:
            self.muted_ranges.insert(i, (start_frame, end_frame))

    def _remove_muted_range(self, start_frame: int, end_frame: int) -> None:
        """
        Remove a muted range, splitting existing ranges if necessary.
        """
        first_index = None
        last_index = None
        for i, (existing_start, existing_end) in enumerate(self.muted_ranges):
            if first_index is None and existing_start <= start_frame <= existing_end:
                if existing_start == start_frame:
                    first_index = i
                else:
                    # keep left part by shortening this range's end
                    first_index = i + 1
                    left_start, _ = self.muted_ranges[i]
                    self.muted_ranges[i] = (left_start, start_frame)

            if first_index is not None and end_frame <= existing_start:
                last_index = i - 1
                _, right_end = self.muted_ranges[last_index]
                if right_end == end_frame:
                    # entire last range is removed
                    last_index = i
                else:
                    # keep right part by moving its start
                    self.muted_ranges[last_index] = (end_frame, right_end)
                break

        if first_index is not None:
            last_index = last_index if last_index is not None else len(self.muted_ranges)
            self.muted_ranges = self.muted_ranges[:first_index] + self.muted_ranges[last_index:]


class Recording(object):
    """
    Original recording with possible trimmed margins.
    """
    def __init__(self, audio_path: str, start_frame: int = 0, num_frames: Optional[int] = None):
        super(Recording, self).__init__()
        self.audio_path = audio_path
        wf = WaveFile(audio_path)
        self.last_frame = wf.end  # total frames in file

        self.start_frame = start_frame
        num_frames = num_frames if num_frames is not None else self.last_frame - start_frame

        self.trimmed = WaveBuffer(audio_path, self.start_frame, num_frames)

    def get_num_frames(self) -> int:
        return self.trimmed.get_num_frames()

    def get_generator(self, frame_offset: int = 0, loop: bool = False) -> WaveGenerator:
        gen = WaveGenerator(self.trimmed, loop)

        gen.frame = frame_offset
        gen.set_gain(0.5)
        return gen

    def set_left_margin(self, start_frame: int) -> None:
        shift = start_frame - self.start_frame
        self.start_frame += shift
        num_frames = self.get_num_frames() - shift

        self.trimmed = WaveBuffer(self.audio_path, self.start_frame, num_frames)

    def set_right_margin(self, end_frame: int) -> None:
        num_frames = end_frame - self.start_frame
        self.trimmed = WaveBuffer(self.audio_path, self.start_frame, num_frames)

    def shift(self, num_frames: int) -> None:
        tot = self.get_num_frames()
        new_start = self.start_frame + num_frames
        new_end = new_start + tot

        # clamp to [0, last_frame]
        if new_start < 0:
            new_start = 0
        elif new_end > self.last_frame:
            new_start = self.last_frame - tot

        self.trimmed = WaveBuffer(self.audio_path, new_start, tot)

class Loop(object):
    """
    Runtime per-animal loop.
    """
    def __init__(self, audio_data: np.ndarray, start_frame: int, num_frames: int, midi: int, role: str, volume: float = 0.5, loop_instances: list[LoopInstance] = []):
        super(Loop, self).__init__()
        self.current = audio_data

        self.start_frame = start_frame # start frame within the recording
        self.num_frames = num_frames # number of frames in the trimmed recording
        self.midi = midi
        self.volume = volume
        self.role = role

        self.instances: Dict[int, RuntimeLoopInstance] = {}
        for loop in loop_instances:
            shifted_data = tune_to_midi(self.current, self.midi, loop.midi)
            self.instances[loop.start_slot] = RuntimeLoopInstance(shifted_data, loop.midi, loop.muted_ranges)
            
    def _has_overlap(
        self,
        candidate_start: int,
        candidate_num_slots: int,
        frame_to_slot: Callable[[int], int],
        ignore_start: Optional[int] = None,
    ) -> bool:
        candidate_end = candidate_start + candidate_num_slots

        for start_slot, num_slots, _ in self.get_instances_info(frame_to_slot):
            if ignore_start is not None and start_slot == ignore_start:
                continue

            existing_start = start_slot
            existing_end = start_slot + num_slots

            # intervals overlap if they are NOT (disjoint on left or right)
            if not (candidate_end <= existing_start or candidate_start >= existing_end):
                return True

        return False

    def get_num_frames(self, slot: int) -> int:
        return self.instances[slot].num_frames
    
    def get_instance_info(self, start_slot: int, frame_to_slot: Callable[[int], int]) -> Tuple[int, int]:
        instance = self.instances[start_slot]
        return (frame_to_slot(instance.num_frames), instance.midi)

    def get_instances_info(self, frame_to_slot: Callable[[int], int]) -> List[Tuple[int, int, int]]:
        return [(start_slot, frame_to_slot(instance.num_frames), instance.midi) for start_slot, instance in self.instances.items()]

    def get_generator(self, start_slot: int, frame_offset: int = 0, loop: bool = False) -> WaveGenerator:
        instance = self.instances[start_slot]
        gen = WaveGenerator(instance, loop)

        gen.frame = frame_offset
        gen.set_gain(self.volume)

        return gen

    def set_volume(self, volume: float) -> None:
        self.volume = max(0.0, min(1.0, volume))

    def set_pitch(self, start_slot: int, midi: int) -> None:
        shifted_data = tune_to_midi(self.current, self.midi, midi)
        self.instances[start_slot].set_buffer(shifted_data, midi)
        
    def add_to_grid(self, start_slot: int, frame_to_slot: Callable[[int], int], overlap: bool = False, midi: Optional[int] = None) -> bool:
        if start_slot in self.instances or (not overlap and self._has_overlap(start_slot, frame_to_slot(self.num_frames), frame_to_slot)):
            return False
        
        midi = midi if midi is not None else self.midi
        shifted_data = tune_to_midi(self.current, self.midi, midi)
        self.instances[start_slot] = RuntimeLoopInstance(shifted_data, midi)
        return True

    def slide(
        self,
        old_start_slot: int,
        new_start_slot: int,
        frame_to_slot: Callable[[int], int],
        overlap: bool = False,
    ) -> int:
        if new_start_slot in self.instances:
            return old_start_slot
        
        if not overlap:
            num_slots, _ = self.get_instance_info(old_start_slot, frame_to_slot)
            if self._has_overlap(new_start_slot, num_slots, frame_to_slot, ignore_start=old_start_slot):
                return old_start_slot
            
        self.instances[new_start_slot] = self.instances.pop(old_start_slot)
        return new_start_slot
    
    def toggle_mute(self, start_slot: int, frame_1: int, frame_2: int, mute: bool) -> None:
        if frame_1 > frame_2:
            frame_1, frame_2 = frame_2, frame_1
        self.instances[start_slot].toggle_mute(frame_1, frame_2, mute)
