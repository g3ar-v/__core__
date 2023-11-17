import audioop
import math
import typing
from collections import deque
from dataclasses import dataclass
from enum import Enum
from os.path import dirname, join

import numpy as np
import onnxruntime

from core import LOG


class SilenceResultType(str, Enum):
    SILENCE = "silence"
    SPEECH = "speech"
    TIMEOUT = "timeout"

    PHRASE_START = "phrase_start"
    PHRASE_END = "phrase_end"


@dataclass
class SilenceResult:
    type: SilenceResultType
    energy: float


class SilenceDetector:
    """
    Detect speech/silence using Silero VAD

    sample_rate: int = 16000
        Sample rate of audio chunks (hertz)

    chunk_size: int = 960
        Must be 30, 60, or 100 ms in duration

    skip_seconds: float = 0
        Seconds of audio to skip before voice command detection starts

    speech_seconds: float = 0.3
        Seconds of speech before voice command has begun

    before_seconds: float = 0.5
        Seconds of audio to keep before voice command has begun

    min_seconds: float = 1.0
        Minimum length of voice command (seconds)

    max_seconds: Optional[float] = 30.0
        Maximum length of voice command before timeout (seconds, None for no timeout)

    silence_seconds: float = 0.5
        Seconds of silence before a voice command has finished

    max_energy: Optional[float] = None
        Maximum denoise energy value (None for dynamic setting from observed audio)

    max_current_ratio_threshold: Optional[float] = None
        Ratio of max/current energy below which audio is considered speech

    current_energy_threshold: Optional[float] = None
        Energy threshold above which audio is considered speech

    """

    def __init__(
        self,
        sample_rate: int = 16000,
        chunk_size: int = 960,
        skip_seconds: float = 0,
        min_seconds: float = 1,
        max_seconds: typing.Optional[float] = 30,
        speech_seconds: float = 0.3,
        silence_seconds: float = 0.5,
        before_seconds: float = 0.5,
        max_energy: typing.Optional[float] = None,
        max_current_ratio_threshold: typing.Optional[float] = None,
        current_energy_threshold: typing.Optional[float] = None,
        vad_config=None,
    ):
        self.sample_rate = sample_rate
        self.sample_width = 2  # 16-bit
        self.sample_channels = 1  # mono
        self.chunk_size = chunk_size
        self.skip_seconds = skip_seconds
        self.min_seconds = min_seconds
        self.max_seconds = max_seconds
        self.speech_seconds = speech_seconds
        self.silence_seconds = silence_seconds
        self.before_seconds = before_seconds

        self.max_energy = max_energy
        self.dynamic_max_energy = max_energy is None
        self.max_current_ratio_threshold = max_current_ratio_threshold
        self.current_energy_threshold = current_energy_threshold
        self.vad_config = vad_config

        # Voice detector
        try:
            self.vad = SileroVAD(self.vad_config)
        except Exception as e:
            LOG.error("Failed to load VAD: " + repr(e))
        self.seconds_per_buffer = (
            self.chunk_size / self.sample_width
        ) / self.sample_rate

        # store some number of seconds of audio data immediately before voice commands
        self.before_buffers = int(
            math.ceil(self.speech_seconds / self.seconds_per_buffer)
        )

        # Pre-compute values
        self.speech_buffers = int(
            math.ceil(self.speech_seconds / self.seconds_per_buffer)
        )

        self.skip_buffers = int(math.ceil(self.skip_seconds / self.seconds_per_buffer))

        # State
        self.before_phrase_chunks: typing.Deque[bytes] = deque(
            maxlen=self.before_buffers
        )
        self.phrase_buffer: bytes = bytes()
        self.max_buffers: typing.Optional[int] = None

    def start(self):
        """Begin new voice command."""

        # State
        self.before_phrase_chunks.clear()
        self.phrase_buffer = bytes()

        if self.max_seconds:
            self.max_buffers = int(
                math.ceil(self.max_seconds / self.seconds_per_buffer)
            )
        else:
            self.max_buffers = None

        self.min_phrase_buffers = int(
            math.ceil(self.min_seconds / self.seconds_per_buffer)
        )
        self.speech_buffers_left = self.speech_buffers
        self.skip_buffers_left = self.skip_buffers
        self.in_phrase = False
        self.after_phrase = False
        self.silence_buffers = int(
            math.ceil(self.silence_seconds / self.seconds_per_buffer)
        )
        self.current_seconds: float = 0
        self.current_chunk: bytes = bytes()

    def stop(self, phrase_only=False) -> bytes:
        """Free resources and return recorded audio"""
        before_buffer = bytes()
        for before_chunk in self.before_phrase_chunks:
            before_buffer += before_chunk

        if phrase_only:
            # NOTE: is 5 a good magic number ?
            # the aim is to include just a tiny bit of silence
            # and avoid super long recordings to account
            # for non streaming STT
            before_buffer = before_chunk[-5:]

        audio_data = before_buffer + self.phrase_buffer

        # Clear state
        self.before_phrase_chunks.clear()
        self.phrase_buffer = bytes()
        self.current_chunk = bytes()

        # Return leftover audio
        return audio_data

    def process(self, audio_chunk: bytes) -> SilenceResult:
        """Process a single chunk of audio data."""
        result: typing.Optional[SilenceResult] = None
        is_speech = False
        energy = SilenceDetector.get_debiased_energy(audio_chunk)

        # Add to overall buffer
        self.current_chunk += audio_chunk

        # Process audio in exact chunk(s)
        while len(self.current_chunk) > self.chunk_size:
            # Extract chunk
            chunk = self.current_chunk[: self.chunk_size]
            self.current_chunk = self.current_chunk[self.chunk_size :]
            if self.skip_buffers_left > 0:
                # Skip audio at beginning
                self.skip_buffers_left -= 1
                continue

            if self.in_phrase:
                self.phrase_buffer += chunk
            else:
                self.before_phrase_chunks.append(chunk)

            self.current_seconds += self.seconds_per_buffer

            # Check maximum number of seconds to record
            if self.max_buffers:
                self.max_buffers -= 1
                if self.max_buffers <= 0:
                    # Timeout
                    return SilenceResult(type=SilenceResultType.TIMEOUT, energy=energy)

            # Detect speech in chunk
            is_speech = not self.is_silence(chunk, energy=energy)

            # Handle state changes
            if is_speech and self.speech_buffers_left > 0:
                self.speech_buffers_left -= 1
            elif is_speech and not self.in_phrase:
                # Start of phrase
                result = SilenceResult(
                    type=SilenceResultType.PHRASE_START, energy=energy
                )

                self.in_phrase = True
                self.after_phrase = False
                self.min_phrase_buffers = int(
                    math.ceil(self.min_seconds / self.seconds_per_buffer)
                )
            elif self.in_phrase and (self.min_phrase_buffers > 0):
                # In phrase, before minimum seconds
                self.min_phrase_buffers -= 1
            elif not is_speech:
                # Outside of speech
                if not self.in_phrase:
                    # Reset
                    self.speech_buffers_left = self.speech_buffers
                elif self.after_phrase and (self.silence_buffers > 0):
                    # After phrase, before stop
                    self.silence_buffers -= 1
                elif self.after_phrase and (self.silence_buffers <= 0):
                    # Phrase complete
                    # Merge before/during command audio data
                    before_buffer = bytes()
                    for before_chunk in self.before_phrase_chunks:
                        before_buffer += before_chunk

                    return SilenceResult(
                        type=SilenceResultType.PHRASE_END, energy=energy
                    )
                elif self.in_phrase and (self.min_phrase_buffers <= 0):
                    # Transition to after phrase
                    self.after_phrase = True
                    self.silence_buffers = int(
                        math.ceil(self.silence_seconds / self.seconds_per_buffer)
                    )

        if result is None:
            # Report speech/silence
            result = SilenceResult(
                type=SilenceResultType.SPEECH
                if is_speech
                else SilenceResultType.SILENCE,
                energy=energy,
            )

        return result

    def is_silence(self, chunk: bytes, energy: typing.Optional[float] = None) -> bool:
        """True if audio chunk contains silence."""
        all_silence = True

        # if self.use_vad:
        # assert self.vad is not None
        all_silence = all_silence and self.vad.is_silent(chunk)

        # if self.use_ratio or self.use_current:
        # Compute debiased energy of audio chunk
        if energy is None:
            energy = SilenceDetector.get_debiased_energy(chunk)

            if self.use_ratio:
                # Ratio of max/current energy compared to threshold
                if self.dynamic_max_energy:
                    # Overwrite max energy
                    if self.max_energy is None:
                        self.max_energy = energy
                    else:
                        self.max_energy = max(energy, self.max_energy)

                assert self.max_energy is not None
                if energy > 0:
                    ratio = self.max_energy / energy
                else:
                    # Not sure what to do here
                    ratio = 0

                assert self.max_current_ratio_threshold is not None
                all_silence = all_silence and (ratio > self.max_current_ratio_threshold)
            elif self.use_current:
                # Current energy compared to threshold
                assert self.current_energy_threshold is not None
                all_silence = all_silence and (energy < self.current_energy_threshold)

        return all_silence

    @staticmethod
    def get_debiased_energy(audio_data: bytes) -> float:
        """Compute RMS of debiased audio."""
        # Thanks to the speech_recognition library!
        # https://github.com/Uberi/speech_recognition/blob/master/speech_recognition/__init__.py
        energy = -audioop.rms(audio_data, 2)
        energy_bytes = bytes([energy & 0xFF, (energy >> 8) & 0xFF])
        debiased_energy = audioop.rms(
            audioop.add(audio_data, energy_bytes * (len(audio_data) // 2), 2), 2
        )

        # Probably actually audio if > 30
        return debiased_energy


class SileroVoiceActivityDetector:
    """Detects speech/silence using Silero VAD.

    https://github.com/snakers4/silero-vad
    """

    def __init__(self, onnx_path):
        self.session = onnxruntime.InferenceSession(onnx_path)
        self.session.intra_op_num_threads = 1
        self.session.inter_op_num_threads = 1

        self.reset()

    def reset(self):
        self._h = np.zeros((2, 1, 64)).astype("float32")
        self._c = np.zeros((2, 1, 64)).astype("float32")

    def __call__(self, audio_array: np.ndarray, sample_rate: int = 16000):
        """Return probability of speech in audio [0-1].

        Audio must be 16Khz 16-bit mono PCM.
        """
        if len(audio_array.shape) == 1:
            # Add batch dimension
            audio_array = np.expand_dims(audio_array, 0)

        if len(audio_array.shape) > 2:
            raise ValueError(
                f"Too many dimensions for input audio chunk {audio_array.dim()}"
            )

        if audio_array.shape[0] > 1:
            raise ValueError("Onnx model does not support batching")

        if sample_rate != 16000:
            raise ValueError("Only 16Khz audio is supported")

        ort_inputs = {
            "input": audio_array.astype(np.float32),
            "h0": self._h,
            "c0": self._c,
        }
        ort_outs = self.session.run(None, ort_inputs)
        out, self._h, self._c = ort_outs

        out = out.squeeze(2)[:, 1]  # make output type match JIT analog

        return out


class SileroVAD:
    def __init__(self, config=None, sample_rate=None):
        model = join(dirname(__file__), "silero_vad.onnx")
        self.vad_threshold = config.get("threshold", 0.2)
        self.vad = SileroVoiceActivityDetector(model)

    def reset(self):
        self.vad.reset()

    def is_silent(self, chunk):
        audio_array = np.frombuffer(chunk, dtype=np.int16)
        return self.vad(audio_array)[0] < self.vad_threshold


# NOTE: has this become redundant?
class NoiseTracker:
    """Noise tracker, used to deterimine if an audio utterance is complete.

    The current implementation expects a number of loud chunks (not necessary
    in one continous sequence) followed by a short period of continous quiet
    audio data to be considered complete.

    Args:
        minimum (int): lower noise level will be threshold for "quiet" level
        maximum (int): ceiling of noise level
        sec_per_buffer (float): the length of each buffer used when updating
                                the tracker
        loud_time_limit (float): time in seconds of low noise to be considered
                                 a complete sentence
        silence_time_limit (float): time limit for silence to abort sentence
        silence_after_loud (float): time of silence to finalize the sentence.
                                    default 0.25 seconds.
    """

    def __init__(
        self,
        minimum,
        maximum,
        sec_per_buffer,
        loud_time_limit,
        silence_time_limit,
        silence_after_loud_time=0.25,
    ):
        self.min_level = minimum
        self.max_level = maximum
        self.sec_per_buffer = sec_per_buffer

        self.num_loud_chunks = 0
        self.level = 0

        # Smallest number of loud chunks required to return loud enough
        self.min_loud_chunks = int(loud_time_limit / sec_per_buffer)

        self.max_silence_duration = silence_time_limit
        self.silence_duration = 0

        # time of quite period after long enough loud data to consider the
        # sentence complete
        self.silence_after_loud = silence_after_loud_time

        # Constants
        self.increase_multiplier = 200
        self.decrease_multiplier = 100

    def _increase_noise(self):
        """Bumps the current level.

        Modifies the noise level with a factor depending in the buffer length.
        """
        if self.level < self.max_level:
            self.level += self.increase_multiplier * self.sec_per_buffer

    def _decrease_noise(self):
        """Decrease the current level.

        Modifies the noise level with a factor depending in the buffer length.
        """
        if self.level > self.min_level:
            self.level -= self.decrease_multiplier * self.sec_per_buffer

    def update(self, is_loud):
        """Update the tracking. with either a loud chunk or a quiet chunk.

        Args:
            is_loud: True if a loud chunk should be registered
                     False if a quiet chunk should be registered
        """
        if is_loud:
            self._increase_noise()
            self.num_loud_chunks += 1
        else:
            self._decrease_noise()
        # Update duration of energy under the threshold level
        if self._quiet_enough():
            self.silence_duration += self.sec_per_buffer
        else:  # Reset silence duration
            self.silence_duration = 0

    def _loud_enough(self):
        """Check if the noise loudness criteria is fulfilled.

        The noise is considered loud enough if it's been over the threshold
        for a certain number of chunks (accumulated, not in a row).
        """
        return self.num_loud_chunks > self.min_loud_chunks

    def _quiet_enough(self):
        """Check if the noise quietness criteria is fulfilled.

        The quiet level is instant and will return True if the level is lower
        or equal to the minimum noise level.
        """
        return self.level <= self.min_level

    def recording_complete(self):
        """Has the end creteria for the recording been met.

        If the noise level has decresed from a loud level to a low level
        the user has stopped speaking.

        Alternatively if a lot of silence was recorded without detecting
        a loud enough phrase.
        """
        too_much_silence = self.silence_duration > self.max_silence_duration
        if too_much_silence:
            LOG.debug("Too much silence recorded without start of sentence " "detected")
        return (
            self._quiet_enough() and self.silence_duration > self.silence_after_loud
        ) and (self._loud_enough() or too_much_silence)
