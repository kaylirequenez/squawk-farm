#####################################################################
#
# This software is to be used for MIT's class Interactive Music Systems only.
# Since this file may contain answers to homework problems, you MAY NOT release it publicly.
#
#####################################################################

import os
import pathlib

import fluidsynth
import numpy as np

from .audio import Audio

FluidR3_GM_URL = "https://www.dropbox.com/scl/fi/jv852ge2ccyhk3nag03sg/FluidR3_GM.sf2?rlkey=s7wmk23cni3r9r9ky0sgyr9wf&dl=1"


# create another kind of generator that generates audio based on the fluid
# synth synthesizer
class Synth(fluidsynth.Synth, object):

    def __init__(self, filepath=None, gain=0.8):
        """Generator that creates sounds from a FluidSynth synthesizer bank.

        :param filepath: Path to the file containing the synthesizer bank. If ``None``, Synth will load a locally cahced FluidR3_GM.sf2 file. If uncached, Synth will download FluidR3_GMsf2.
        :param gain: The gain, a float between 0 and 1.
        """

        super(Synth, self).__init__(gain, samplerate=float(Audio.sample_rate))
        if filepath is None:
            filepath = self._get_cached_fluidbank()
        self.sfid = self.sfload(filepath)
        if self.sfid == -1:
            raise Exception("Error in fluidsynth.sfload(): cannot open " + filepath)

        # set default sound for each channel upfront
        for channel in range(16):
            self.program(channel, 0, 0)

    def program(self, chan, bank, preset):
        """
        Essentially defines which instrument this generator's synth uses.
        Specific *bank* and *preset* combinations can be used to switch between different instruments.

        :param chan: The channel to use for audio playback.
        :param bank: The sound bank to use.
        :param preset: The preset to use.
        """

        self.program_select(chan, self.sfid, bank, preset)

    def generate(self, num_frames, num_channels):
        """
        Generates and returns frames. Should be called every frame.

        :param num_frames: An integer number of frames to generate.
        :param num_channels: Number of channels. Can be 1 (mono) or 2 (stereo)

        :returns: A tuple ``(output, True)``. The output is a numpy array of length
            **(num_frames * num_channels)**
        """

        assert num_channels == 2
        # get_samples() returns interleaved stereo, so all we have to do is scale
        # the data to [-1, 1].
        samples = self.get_samples(num_frames).astype(np.float32)
        samples *= 1.0 / 32768.0
        return (samples, True)

    def noteon(self, chan, key, vel):
        """
        Plays a note.

        :param chan: The channel to use for audio playback.
        :param key: The midi key to play.
        :param vel: The velocity to play the note at -- correlates with volume.
            Ranges from 0 to 127.
        """
        super().noteon(chan, key, vel)

    def noteoff(self, chan, key):
        """
        Stops a note.

        :param chan: The channel on which the note should be stopped.
        :param key: The key to stop.
        """
        super().noteoff(chan, key)

    def pitch_bend(self, chan, val):
        """
        Adjust pitch for all notes of a channel.
        A pitch bend value of 0 is no pitch change from default.
        For the default setting of +/- 2 semitones:
        - A value of -4096 is 1 semitone down.
        - A value of 4096 is 1 semitone up.
        Maximum values are -8192 to +8192.
        See :func:`Synth.set_pitchbend_range` to adjust the semitone range.

        :param chan: The channel to use for audio playback.
        :param val: The value to adjust pitch by, as specified above.
        """
        super().pitch_bend(chan, val)

    def cc(self, chan, ctrl, val):
        """
        Send control change value. The controls that are recognized
        are dependent on the SoundFont.
        Typical values include -

            | 1 : vibrato
            | 7 : volume
            | 10 : pan (left to right)
            | 11 : expression (soft to loud)
            | 64 : sustain
            | 91 : reverb
            | 93 : chorus

        :param chan: The channel to use for audio playback.
        :param ctrl: The control to modify, examples provided above.
        :param val: The new value for the control. Always ranges 0 to 127.
        """
        super().cc(chan, ctrl, val)

    def set_pitchbend_range(self, chan, semitones):
        """The default pitchbend range is +/- 2 semitones. Use this to set a new pitchbend range
        for the given channel.

        :param chan: The channel this function controls.
        :param semitones: The number of +/- semitones to set the pitchbend range.
        """

        self.cc(chan, 101, 0)
        self.cc(chan, 100, 0)
        self.cc(chan, 6, int(semitones))
        self.cc(chan, 38, 0)

    def _get_cached_fluidbank(self):
        """find cached file, or download first if necessary"""
        filename = "FluidR3_GM.sf2"
        cachedir = os.path.join(str(pathlib.Path.home()), ".ims")
        filepath = os.path.join(cachedir, filename)

        # file does not exist, so get a copy
        if not os.path.exists(filepath):
            from urllib.request import urlretrieve

            if not os.path.exists(cachedir):
                os.makedirs(cachedir)

            tmp_filename = "FluidR3_GM.sf2.tmp"
            tmp_filepath = os.path.join(cachedir, tmp_filename)

            def progress(num_blocks, block_size, total_size):
                pct = int(100 * num_blocks * block_size / total_size)
                txt = f"Downloading {filename}: {pct}%"
                print(txt, end="\r", flush=True)

            # download to a temporary file, then rename it
            # this means that if the user stops the download, the file won't be left in a corrupted state
            urlretrieve(url=FluidR3_GM_URL, filename=tmp_filepath, reporthook=progress)
            os.rename(tmp_filepath, filepath)
            print("Done")

        return filepath
