"""Factory functions for loading hotword engines - both internal and plugins.
"""

import struct
from os.path import abspath, dirname, expanduser, join
from threading import Thread
from time import sleep

from core.configuration import Configuration

# from mycroft.configuration.locations import OLD_USER_CONFIG
from core.util.log import LOG
from core.util.monotonic_event import MonotonicEvent
from core.util.plugins import load_plugin

RECOGNIZER_DIR = join(abspath(dirname(__file__)), "recognizer")
INIT_TIMEOUT = 10  # In seconds


class TriggerReload(Exception):
    pass


class NoModelAvailable(Exception):
    pass


def msec_to_sec(msecs):
    """Convert milliseconds to seconds.

    Args:
        msecs: milliseconds

    Returns:
        int: input converted from milliseconds to seconds
    """
    return msecs / 1000


class HotWordEngine:
    """Hotword/Wakeword base class to be implemented by all wake word plugins.

    Args:
        key_phrase (str): string representation of the wake word
        config (dict): Configuration block for the specific wake word
        lang (str): language code (BCP-47)
    """

    def __init__(self, key_phrase="hey mycroft", config=None, lang="en-us"):
        self.key_phrase = str(key_phrase).lower()

        if config is None:
            config = Configuration.get().get("voice", {}).get("hotwords", {})
            config = config.get(self.key_phrase, {})
        self.config = config

        # rough estimate 1 phoneme per 2 chars
        self.num_phonemes = len(key_phrase) / 2 + 1
        phoneme_duration = msec_to_sec(config.get("phoneme_duration", 120))
        self.expected_duration = self.num_phonemes * phoneme_duration

        self.listener_config = Configuration.get().get("voice", {}).get("listener", {})
        self.lang = str(self.config.get("lang", lang)).lower()

    def found_wake_word(self, frame_data):
        """Check if wake word has been found.

        Checks if the wake word has been found. Should reset any internal
        tracking of the wake word state.

        Args:
            frame_data (binary data): Deprecated. Audio data for large chunk
                                      of audio to be processed. This should not
                                      be used to detect audio data instead
                                      use update() to incrementaly update audio
        Returns:
            bool: True if a wake word was detected, else False
        """
        return False

    def update(self, chunk):
        """Updates the hotword engine with new audio data.

        The engine should process the data and update internal trigger state.

        Args:
            chunk (bytes): Chunk of audio data to process
        """

    def stop(self):
        """Perform any actions needed to shut down the wake word engine.

        This may include things such as unloading data or shutdown
        external processess.
        """


class PorcupineHotWord(HotWordEngine):
    """Hotword engine using picovoice's Porcupine hot word engine."""

    def __init__(self, key_phrase="hey mycroft", config=None, lang="en-us"):
        super().__init__(key_phrase, config, lang)
        keyword_file_paths = [
            expanduser(x.strip())
            for x in self.config.get("keyword_file_path", "hey_mycroft.ppn").split(",")
        ]
        sensitivities = self.config.get("sensitivities", 0.5)
        access_key = (
            Configuration.get().get("microservices", {}).get("porcupine_api_key", "")
        )

        try:
            import pvporcupine
            from pvporcupine._util import pv_library_path, pv_model_path
        except ImportError as err:
            raise Exception(
                "Python bindings for Porcupine not found. "
                'Please run "pip install pvporcupine"'
            ) from err

        library_path = pv_library_path("")
        model_file_path = pv_model_path("")
        if isinstance(sensitivities, float):
            sensitivities = [sensitivities] * len(keyword_file_paths)
        else:
            sensitivities = [float(x) for x in sensitivities.split(",")]

        self.audio_buffer = []
        self.has_found = False
        self.num_keywords = len(keyword_file_paths)

        LOG.debug(
            "loading porcupine using library path {} and keyword paths {}".format(
                library_path, keyword_file_paths
            )
        )
        self.porcupine = pvporcupine.create(
            library_path=library_path,
            model_path=model_file_path,
            keyword_paths=keyword_file_paths,
            sensitivities=sensitivities,
            access_key=access_key,
        )

        LOG.info("LOADED PORCUPINE")

    def update(self, chunk):
        """Update detection state from a chunk of audio data.

        Args:
            chunk (bytes): Audio data to parse
        """
        pcm = struct.unpack_from("h" * (len(chunk) // 2), chunk)
        self.audio_buffer += pcm
        while True:
            if len(self.audio_buffer) >= self.porcupine.frame_length:
                result = self.porcupine.process(
                    self.audio_buffer[0 : self.porcupine.frame_length]
                )
                # result will be the index of the found keyword or -1 if
                # nothing has been found.
                self.has_found |= result >= 0
                self.audio_buffer = self.audio_buffer[self.porcupine.frame_length :]
            else:
                return

    def found_wake_word(self, frame_data):
        """Check if wakeword has been found.

        Returns:
            (bool) True if wakeword was found otherwise False.
        """
        if self.has_found:
            self.has_found = False
            return True
        return False

    def stop(self):
        """Stop the hotword engine.

        Clean up Porcupine library.
        """
        if self.porcupine is not None:
            self.porcupine.delete()


def load_wake_word_plugin(module_name):
    """Wrapper function for loading wake word plugin.

    Args:
        (str) Mycroft wake word module name from config
    """
    return load_plugin("mycroft.plugin.wake_word", module_name)


class HotWordFactory:
    """Factory class instantiating the configured Hotword engine.

    The factory can select between a range of built-in Hotword engines and also
    from Hotword engine plugins.
    """

    CLASSES = {
        "porcupine": PorcupineHotWord,
    }

    @staticmethod
    def load_module(module, hotword, config, lang, loop):
        LOG.info('Loading "{}" wake word via {}'.format(hotword, module))
        instance = None
        complete = MonotonicEvent()

        def initialize():
            nonlocal instance, complete
            try:
                if module in HotWordFactory.CLASSES:
                    clazz = HotWordFactory.CLASSES[module]
                else:
                    clazz = load_wake_word_plugin(module)
                    LOG.info("LOADED THE WAKE WORD PLUGIN {}".format(module))

                instance = clazz(hotword, config, lang=lang)
            except TriggerReload:
                complete.set()
                sleep(0.5)
                loop.reload()
            except NoModelAvailable:
                LOG.warning(
                    "Could not found find model for {} on {}.".format(hotword, module)
                )
                instance = None

            except Exception:
                LOG.exception("Could not create hotword. Falling back to default.")
                instance = None
            complete.set()

        Thread(target=initialize, daemon=True).start()
        if not complete.wait(INIT_TIMEOUT):
            LOG.info("{} is taking too long to load".format(module))
            complete.set()
        return instance

    @classmethod
    def create_hotword(
        cls, hotword="hey mycroft", config=None, lang="en-us", loop=None
    ):
        if not config:
            config = Configuration.get()["voice"]["hotwords"]
        config = config.get(hotword) or config["hey mycroft"]

        module = config.get("module", "precise")
        return (
            cls.load_module(module, hotword, config, lang, loop)
            or cls.load_module("porcupine", hotword, config, lang, loop)
            or cls.CLASSES["porcupine"]()
        )
