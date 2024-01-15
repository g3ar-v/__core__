from abc import ABCMeta, abstractmethod

from core.configuration import Configuration
from speech_recognition import Recognizer


class STT(metaclass=ABCMeta):
    """STT Base class, all STT backends derive from this one."""

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
