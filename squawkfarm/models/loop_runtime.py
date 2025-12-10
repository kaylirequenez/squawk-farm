from imslib.wavegen import WaveGenerator
from imslib.wavesrc import WaveBuffer, WaveFile

from squawkfarm.utils import tune_to_midi
from squawkfarm.utils.audio_utils import fade_in_out


class Recording(object):
    def __init__(self, audio_path, start_frame=0, num_frames=None):
        super(Recording, self).__init__()
        self.audio_path = audio_path
        wf = WaveFile(audio_path)
        self.last_frame = wf.end

        self.start_frame = start_frame
        num_frames = (
            num_frames if num_frames is not None else self.last_frame - start_frame
        )

        self.trimmed = WaveBuffer(audio_path, self.start_frame, num_frames)
        self.trimmed.data = fade_in_out(self.trimmed.data)
        self.volume = 0.5  # Default volume

    def get_num_frames(self):
        return self.trimmed.get_num_frames()

    def get_generator(self, frame_offset=0, loop=False):
        gen = WaveGenerator(self.trimmed, loop)

        gen.frame = frame_offset
        gen.set_gain(self.volume)
        return gen

    def set_volume(self, volume):
        self.volume = max(0.0, min(1.0, volume))

    def get_volume(self):
        return self.volume

    def set_left_margin(self, start_frame):
        shift = start_frame - self.start_frame
        self.start_frame += shift
        num_frames = self.get_num_frames() - shift

        self.trimmed = WaveBuffer(self.audio_path, self.start_frame, num_frames)
        self.trimmed.data = fade_in_out(self.trimmed.data)

    def set_right_margin(self, end_frame):
        num_frames = end_frame - self.start_frame
        self.trimmed = WaveBuffer(self.audio_path, self.start_frame, num_frames)
        self.trimmed.data = fade_in_out(self.trimmed.data)

    def shift(self, num_frames):
        tot = self.get_num_frames()
        new_start = self.start_frame + num_frames
        new_end = new_start + tot

        if new_start < 0:
            new_start = 0
        elif new_end > self.last_frame:
            new_start = self.last_frame - tot

        self.trimmed = WaveBuffer(self.audio_path, new_start, tot)


class RuntimeLoopInstance(object):
    def __init__(self, data, muted_ranges=None):
        super(RuntimeLoopInstance, self).__init__()
        self.muted_ranges = muted_ranges if muted_ranges else []
        self.set_buffer(data)

    def set_buffer(self, data):
        self.clean_data = data.copy()
        self.data = data.copy()
        self.num_frames = len(self.data)
        self.num_channels = 1

        for start_frame, end_frame in self.muted_ranges:
            self.data[start_frame:end_frame] = 0

    def get_frames(self, start_frame, num_frames):
        return self.data[start_frame : start_frame + num_frames]

    def get_num_channels(self):
        return self.num_channels

    def toggle_mute(self, start_frame, end_frame, mute):
        start_frame = max(0, start_frame)
        end_frame = min(self.num_frames, end_frame)

        if mute:
            self.data[start_frame:end_frame] = 0
            self._add_muted_range(start_frame, end_frame)
        else:
            self.data[start_frame:end_frame] = self.clean_data[start_frame:end_frame]
            self._remove_muted_range(start_frame, end_frame)

    def _add_muted_range(self, start_frame, end_frame):
        i, overlap = 0, False
        while not overlap and i < len(self.muted_ranges):
            existing_start, existing_end = self.muted_ranges[i]
            if existing_start <= start_frame <= existing_end:
                j = i + 1
                while (
                    j < len(self.muted_ranges) and end_frame >= self.muted_ranges[j][0]
                ):
                    j += 1
                end_frame = max(end_frame, self.muted_ranges[j - 1][1])
                self.muted_ranges[i:j] = [(existing_start, end_frame)]
                overlap = True
            else:
                i += 1

        if not overlap:
            self.muted_ranges.insert(i, (start_frame, end_frame))

    def _remove_muted_range(self, start_frame, end_frame):
        first_index = None
        last_index = None
        for i, (existing_start, existing_end) in enumerate(self.muted_ranges):
            if first_index is None and existing_start <= start_frame <= existing_end:
                if existing_start == start_frame:
                    first_index = i
                else:
                    first_index = i + 1
                    left_start, _ = self.muted_ranges[i]
                    self.muted_ranges[i] = (left_start, start_frame)

            if first_index is not None and end_frame <= existing_start:
                last_index = i - 1
                _, right_end = self.muted_ranges[last_index]
                if right_end == end_frame:
                    last_index = i
                else:
                    self.muted_ranges[last_index] = (end_frame, right_end)
                break

        if first_index is not None:
            last_index = (
                last_index if last_index is not None else len(self.muted_ranges)
            )
            self.muted_ranges = (
                self.muted_ranges[:first_index] + self.muted_ranges[last_index:]
            )


class Loop(object):
    def __init__(
        self,
        audio_data,
        start_frame,
        num_frames,
        midi,
        role,
        volume=1,
        loop_instances={},
    ):
        super(Loop, self).__init__()
        self.current = audio_data
        self.start_frame = start_frame
        self.num_frames = num_frames
        self.midi = midi
        self.original_midi = midi  # Track the original MIDI for tuning reference
        self.volume = volume
        self.role = role

        self.octave_shift = 0

        self.instances: dict[int, int] = {}
        loop_instances = loop_instances if loop_instances else []
        for start_slot, midi in loop_instances:
            self.instances[start_slot] = midi

    def _has_overlap(self, candidate_start, frame_to_slot, ignore_start=None):
        num_slots = frame_to_slot(self.num_frames)
        candidate_end = candidate_start + num_slots

        for start_slot in self.instances.keys():
            if ignore_start is not None and start_slot == ignore_start:
                continue

            existing_start = start_slot
            existing_end = start_slot + num_slots

            if not (candidate_end <= existing_start or candidate_start >= existing_end):
                return True

        return False

    def get_generator(self, start_slot, frame_offset=0, loop=False):
        midi = self.instances[start_slot]
        shifted_data = tune_to_midi(self.current, self.original_midi, midi)

        instance = RuntimeLoopInstance(shifted_data)
        gen = WaveGenerator(instance, loop)

        gen.frame = frame_offset
        gen.set_gain(self.volume)
        return gen

    def set_volume(self, volume):
        self.volume = max(0.0, min(1.0, volume))

    def set_pitch(self, start_slot, midi):
        self.instances[start_slot] = midi

    def add_to_grid(self, start_slot, frame_to_slot, overlap=False, midi=None):
        if start_slot in self.instances or (
            not overlap and self._has_overlap(start_slot, frame_to_slot)
        ):
            return False

        midi = midi if midi is not None else self.midi
        self.instances[start_slot] = midi
        return True

    def slide(self, old_start_slot, new_start_slot, frame_to_slot, overlap=False):
        if new_start_slot in self.instances:
            return old_start_slot

        if not overlap and self._has_overlap(
            new_start_slot, frame_to_slot, ignore_start=old_start_slot
        ):
            return old_start_slot

        self.instances[new_start_slot] = self.instances.pop(old_start_slot)
        return new_start_slot
