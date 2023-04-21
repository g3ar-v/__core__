import re
import json
from abc import ABCMeta, abstractmethod
from requests import post, put, exceptions
from speech_recognition import Recognizer
from queue import Queue
from threading import Thread

from core.api import STTApi, HTTPError
from core.configuration import Configuration
from core.util.log import LOG
from core.util.plugins import load_plugin


class STT(metaclass=ABCMeta):
    """STT Base class, all STT backends derive from this one. """
    def __init__(self):
        config_core = Configuration.get()
        self.lang = str(self.init_language(config_core))
        config_stt = config_core.get("stt", {})
        self.config = config_stt.get(config_stt.get("module"), {})
        self.credential = self.config.get("credential", {})
        self.recognizer = Recognizer()
        self.can_stream = False

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


def requires_pairing(func):
    """Decorator kicking of pairing sequence if client is not allowed access.

    Checks the http status of the response if an HTTP error is recieved. If
    a 401 status is detected returns "pair my device" to trigger the pairing
    skill.
    """
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except HTTPError as e:
            if e.response.status_code == 401:
                LOG.warning('Access Denied at mycroft.ai')
                # phrase to start the pairing process
                return 'pair my device'
            else:
                raise
    return wrapper


class MycroftSTT(STT):
    """Default mycroft STT."""
    def __init__(self):
        super(MycroftSTT, self).__init__()
        self.api = STTApi("stt")

    @requires_pairing
    def execute(self, audio, language=None):
        self.lang = language or self.lang
        try:
            return self.api.stt(audio.get_flac_data(convert_rate=16000),
                                self.lang, 1)[0]
        except Exception:
            return self.api.stt(audio.get_flac_data(), self.lang, 1)[0]


def load_stt_plugin(module_name):
    """Wrapper function for loading stt plugin.

    Args:
        module_name (str): Mycroft stt module name from config
    Returns:
        class: STT plugin class
    """
    return load_plugin('mycroft.plugin.stt', module_name)


class STTFactory:
    CLASSES = {
        "mycroft": MycroftSTT,
        # "google": GoogleSTT,
        # "google_cloud": GoogleCloudSTT,
        # "google_cloud_streaming": GoogleCloudStreamingSTT,
        # "wit": WITSTT,
        # "ibm": IBMSTT,
        # "kaldi": KaldiSTT,
        # "bing": BingSTT,
        # "govivace": GoVivaceSTT,
        # "houndify": HoundifySTT,
        # "deepspeech_server": DeepSpeechServerSTT,
        # "deepspeech_stream_server": DeepSpeechStreamServerSTT,
        # "mycroft_deepspeech": MycroftDeepSpeechSTT,
        # "yandex": YandexSTT
    }

    @staticmethod
    def create():
        try:
            config = Configuration.get().get("stt", {})
            module = config.get("module", "mycroft")
            if module in STTFactory.CLASSES:
                clazz = STTFactory.CLASSES[module]
            else:
                clazz = load_stt_plugin(module)
                LOG.info('Loaded the STT plugin {}'.format(module))
            return clazz()
        except Exception:
            # The STT backend failed to start. Report it and fall back to
            # default.
            LOG.exception('The selected STT backend could not be loaded, '
                          'falling back to default...')
            if module != 'mycroft':
                return MycroftSTT()
            else:
                raise
