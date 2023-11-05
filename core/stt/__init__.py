import time
import numpy as np
from abc import ABCMeta, abstractmethod
from typing import List
from speech_recognition import Recognizer, AudioData

from threading import Event
from faster_whisper import WhisperModel, decode_audio
from core.configuration import Configuration
from core.util.log import LOG
from core.util.plugins import load_plugin


class ReadWriteStream:
    """
    Class used to support writing binary audio data at any pace,
    optionally chopping when the buffer gets too large
    """

    def __init__(self, s=b"", chop_samples=-1):
        self.buffer = s
        self.write_event = Event()
        self.chop_samples = chop_samples

    def __len__(self):
        return len(self.buffer)

    def read(self, n=-1, timeout=None):
        if n == -1:
            n = len(self.buffer)
        if 0 < self.chop_samples < len(self.buffer):
            samples_left = len(self.buffer) % self.chop_samples
            self.buffer = self.buffer[-samples_left:]
        return_time = 1e10 if timeout is None else (timeout + time.time())
        while len(self.buffer) < n:
            self.write_event.clear()
            if not self.write_event.wait(return_time - time.time()):
                return b""
        chunk = self.buffer[:n]
        self.buffer = self.buffer[n:]
        return chunk

    def write(self, s):
        self.buffer += s
        self.write_event.set()

    def flush(self):
        """Makes compatible with sys.stdout"""
        pass

    def clear(self):
        self.buffer = b""


class AudioTransformer:
    """process audio data and optionally transform it before STT stage"""

    def __init__(self, name, priority=50, config=None):
        self.name = name
        self.bus = None
        self.priority = priority
        self.config = config or self._read_mycroft_conf()

        # listener config
        self.sample_width = self.config.get("sample_width", 2)
        self.channels = self.config.get("channels", 1)
        self.sample_rate = self.config.get("sample_rate", 16000)

        # buffers with audio chunks to be used in predictions
        # always cleared before STT stage
        self.noise_feed = ReadWriteStream()
        self.hotword_feed = ReadWriteStream()
        self.speech_feed = ReadWriteStream()

    def _read_mycroft_conf(self):
        config_core = dict(Configuration())
        config = config_core.get("audio_transformers", {}).get(self.name) or {}
        listener_config = config_core.get("listener") or {}
        for k in ["sample_width", "sample_rate", "channels"]:
            if k not in config and k in listener_config:
                config[k] = listener_config[k]
        return config

    def bind(self, bus=None):
        """attach messagebus"""
        # self.bus = bus or get_mycroft_bus()
        self.bus = bus

    def feed_audio_chunk(self, chunk):
        chunk = self.on_audio(chunk)
        self.noise_feed.write(chunk)

    def feed_hotword_chunk(self, chunk):
        chunk = self.on_hotword(chunk)
        self.hotword_feed.write(chunk)

    def feed_speech_chunk(self, chunk):
        chunk = self.on_speech(chunk)
        self.speech_feed.write(chunk)

    def feed_speech_utterance(self, chunk):
        return self.on_speech_end(chunk)

    def reset(self):
        # end of prediction, reset buffers
        self.speech_feed.clear()
        self.hotword_feed.clear()
        self.noise_feed.clear()

    def initialize(self):
        """perform any initialization actions"""
        pass

    def on_audio(self, audio_data):
        """Take any action you want, audio_data is a non-speech chunk"""
        return audio_data

    def on_hotword(self, audio_data):
        """Take any action you want, audio_data is a full wake/hotword
        Common action would be to prepare to received speech chunks
        NOTE: this might be a hotword or a wakeword, listening is not assured
        """
        return audio_data

    def on_speech(self, audio_data):
        """Take any action you want, audio_data is a speech chunk (NOT a
        full utterance) during recording
        """
        return audio_data

    def on_speech_end(self, audio_data):
        """Take any action you want, audio_data is the full speech audio"""
        return audio_data

    def transform(self, audio_data):
        """return any additional message context to be passed in
        recognize_loop:utterance message, usually a streaming prediction
        Optionally make the prediction here with saved chunks from other handlers
        """
        return audio_data, {}

    def default_shutdown(self):
        """perform any shutdown actions"""
        pass


class FasterWhisperLangClassifier(AudioTransformer):
    def __init__(self, config=None):
        config = config or {}
        super().__init__("ovos-audio-transformer-plugin-fasterwhisper", 10, config)
        model = self.config.get("model")
        if not model:
            model = "small"

        assert model in FasterWhisperSTT.MODELS  # TODO - better error handling

        self.compute_type = self.config.get("compute_type", "int8")
        self.use_cuda = self.config.get("use_cuda", False)
        self.beam_size = self.config.get("beam_size", 5)
        self.cpu_threads = self.config.get("cpu_threads", 4)

        if self.use_cuda:
            device = "cuda"
        else:
            device = "cpu"
        self.engine = WhisperModel(model, device=device, compute_type=self.compute_type)

    @property
    def valid_langs(self) -> List[str]:
        # return list(
        #     set([get_default_lang()] + Configuration().get("secondary_langs", []))
        # )
        pass

    @staticmethod
    def audiochunk2array(audio_data):
        # Convert buffer to float32 using NumPy
        audio_as_np_int16 = np.frombuffer(audio_data, dtype=np.int16)
        audio_as_np_float32 = audio_as_np_int16.astype(np.float32)

        # Normalise float32 array so that values are between -1.0 and +1.0
        max_int16 = 2**15
        data = audio_as_np_float32 / max_int16
        return data

    def detect(self, audio, valid_langs=None):
        # valid_langs = [l.lower().split("-")[0] for l in valid_langs or self.valid_langs]

        if not self.engine.model.is_multilingual:
            language = "en"
            language_probability = 1
        else:
            sampling_rate = self.engine.feature_extractor.sampling_rate

            if not isinstance(audio, np.ndarray):
                audio = decode_audio(audio, sampling_rate=sampling_rate)

            features = self.engine.feature_extractor(audio)

            segment = features[:, : self.engine.feature_extractor.nb_max_frames]
            encoder_output = self.engine.encode(segment)
            results = self.engine.model.detect_language(encoder_output)[0]
            results = [(l[2:-2], p) for l, p in results if l[2:-2] in valid_langs]
            total = sum(l[1] for l in results) or 1
            results = sorted(
                [(l, p / total) for l, p in results], key=lambda k: k[1], reverse=True
            )

            language, language_probability = results[0]
        return language, language_probability

    # plugin api
    def transform(self, audio_data):
        lang, prob = self.detect(self.audiochunk2array(audio_data))
        LOG.info(f"Detected speech language '{lang}' with probability {prob}")
        return audio_data, {"stt_lang": lang, "lang_probability": prob}


class STT(metaclass=ABCMeta):
    """STT Base class, all STT backends derive from this one."""

    def __init__(self):
        config_core = Configuration.get()
        self.lang = str(self.init_language(config_core))
        config_stt = config_core.get("stt", {})
        self.config = config_stt.get(config_stt.get("module"), {})
        self.credential = self.config.get("credential", {})
        self.recognizer = Recognizer()
        self.can_stream = True

    @property
    def available_languages(self) -> set:
        """Return languages supported by this STT implementation in this state

        This property should be overridden by the derived class to advertise
        what languages that engine supports.

        Returns:
            set: supported languages
        """
        return set()

    @staticmethod
    def init_language(config_core):
        """Helper method to get language code from Mycroft config."""
        lang = config_core.get("lang", "en-US")
        langs = lang.split("-")
        if len(langs) == 2:
            return langs[0].lower() + "-" + langs[1].upper()
        return lang

    @abstractmethod
    def execute(self, audio, language=None):
        """Implementation of STT functionallity.

        This method needs to be implemented by the derived class to implement
        the specific STT engine connection.

        The method gets passed audio and optionally a language code and is
        expected to return a text string.

        Args:
            audio (AudioData): audio recorded by mycroft.
            language (str): optional language code

        Returns:
            str: parsed text
        """


def load_stt_plugin(module_name):
    """Wrapper function for loading stt plugin.

    Args:
        module_name (str): System stt module name from config
    Returns:
        class: STT plugin class
    """
    return load_plugin("core.plugin.stt", module_name)


# TODO: implement whisper object


class FasterWhisperSTT(STT):
    MODELS = (
        "tiny.en",
        "tiny",
        "base.en",
        "base",
        "small.en",
        "small",
        "medium.en",
        "medium",
        "large",
        "large-v2",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        model = self.config.get("model")
        if not model:
            model = "large-v2"
        assert model in self.MODELS  # TODO - better error handling

        self.beam_size = self.config.get("beam_size", 5)
        self.compute_type = self.config.get("compute_type", "int8")
        self.use_cuda = self.config.get("use_cuda", False)
        self.cpu_threads = self.config.get("cpu_threads", 4)

        if self.use_cuda:
            device = "cuda"
        else:
            device = "cpu"
        self.engine = WhisperModel(
            model,
            device=device,
            compute_type=self.compute_type,
            cpu_threads=self.cpu_threads,
        )

    @staticmethod
    def audiodata2array(audio_data):
        assert isinstance(audio_data, AudioData)
        return FasterWhisperLangClassifier.audiochunk2array(audio_data.get_wav_data())

    def execute(self, audio, language=None):
        lang = language or self.lang
        segments, _ = self.engine.transcribe(
            self.audiodata2array(audio),
            beam_size=self.beam_size,
            condition_on_previous_text=False,
            language=lang.split("-")[0].lower(),
        )
        # segments is an iterator, transcription only happens here
        transcription = "".join(segment.text for segment in segments).strip()
        return transcription


class STTFactory:
    CLASSES = {
        # "google": GoogleSTT,
        "whisper": FasterWhisperSTT,
    }

    @staticmethod
    def create():
        try:
            config = Configuration.get().get("stt", {})
            module = config.get("module", {})
            if module in STTFactory.CLASSES:
                clazz = STTFactory.CLASSES[module]
            else:
                clazz = load_stt_plugin(module)
                LOG.info("Loaded the STT plugin {}".format(module))
            return clazz()
        except Exception:
            # The STT backend failed to start. Report it and fall back to
            # default.
            LOG.exception(
                "The selected STT backend could not be loaded, "
                "falling back to default..."
            )
