"""Factory functions for loading hotword engines - both internal and plugins.
"""
from contextlib import suppress
from glob import glob
import os
from os.path import dirname, exists, join, abspath, expanduser, isfile, isdir
import platform
import posixpath
from shutil import rmtree
import struct
from threading import Timer, Thread
from time import sleep
from urllib.error import HTTPError
import xdg.BaseDirectory

from petact import install_package
import requests

from core.configuration import Configuration, LocalConf

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


class PreciseUnavailable(Exception):
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
            config = Configuration.get().get("hotwords", {})
            config = config.get(self.key_phrase, {})
        self.config = config

        # rough estimate 1 phoneme per 2 chars
        self.num_phonemes = len(key_phrase) / 2 + 1
        phoneme_duration = msec_to_sec(config.get("phoneme_duration", 120))
        self.expected_duration = self.num_phonemes * phoneme_duration

        self.listener_config = Configuration.get().get("listener", {})
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


class PreciseHotword(HotWordEngine):
    """Precise is the default wake word engine for Mycroft.

    Precise is developed by Mycroft AI and produces quite good wake word
    spotting when trained on a decent dataset.
    """

    def __init__(self, key_phrase="hey mycroft", config=None, lang="en-us"):
        super().__init__(key_phrase, config, lang)
        from precise_runner import PreciseRunner, PreciseEngine, ReadWriteStream

        # We need to save to a writeable location, but the key we need
        # might be stored in a different, unwriteable, location
        # Make sure we pick the key we need from wherever it's located,
        # but save to a writeable location only
        local_conf = LocalConf(
            join(xdg.BaseDirectory.xdg_config_home, "mycroft", "mycroft.conf")
        )

        for conf_dir in xdg.BaseDirectory.load_config_paths("mycroft"):
            conf = LocalConf(join(conf_dir, "mycroft.conf"))
            # If the current config contains the precise key use it,
            # otherwise continue to the next file
            if conf.get("precise", None) is not None:
                local_conf["precise"] = conf.get("precise", None)
                break

        # If the key is not found yet, it might still exist on the old
        # (deprecated) location
        # if local_conf.get('precise', None) is None:
        # local_conf = LocalConf(OLD_USER_CONFIG)

        if not local_conf.get("precise", {}).get("use_precise", True):
            raise PreciseUnavailable

        if (
            local_conf.get("precise", {}).get("dist_url")
            == "http://bootstrap.mycroft.ai/artifacts/static/daily/"
        ):
            del local_conf["precise"]["dist_url"]
            local_conf.store()
            Configuration.updated(None)

        self.download_complete = True

        self.show_download_progress = Timer(0, lambda: None)
        precise_config = Configuration.get()["precise"]

        precise_exe = self.update_precise(precise_config)

        local_model = self.config.get("local_model_file")
        if local_model:
            self.precise_model = expanduser(local_model)
        else:
            self.precise_model = self.install_model(
                precise_config["model_url"], key_phrase.replace(" ", "-")
            ).replace(".tar.gz", ".pb")

        self.has_found = False
        self.stream = ReadWriteStream()

        def on_activation():
            self.has_found = True

        trigger_level = self.config.get("trigger_level", 3)
        sensitivity = self.config.get("sensitivity", 0.5)

        self.runner = PreciseRunner(
            PreciseEngine(precise_exe, self.precise_model),
            trigger_level,
            sensitivity,
            stream=self.stream,
            on_activation=on_activation,
        )
        self.runner.start()

    def update_precise(self, precise_config):
        """Continously try to download precise until successful"""
        precise_exe = None
        while not precise_exe:
            try:
                precise_exe = self.install_exe(precise_config["dist_url"])
            except TriggerReload:
                raise
            except Exception as e:
                LOG.error("Precise could not be downloaded({})".format(repr(e)))
                if exists(self.install_destination):
                    precise_exe = self.install_destination
                else:
                    # Wait one minute before retrying
                    sleep(60)
        return precise_exe

    @property
    def folder(self):
        old_path = join(expanduser("~"), ".core", "precise")
        if os.path.isdir(old_path):
            return old_path
        return xdg.BaseDirectory.save_data_path("core", "precise")

    @property
    def install_destination(self):
        return join(self.folder, "precise-engine", "precise-engine")

    def install_exe(self, url: str) -> str:
        url = url.format(arch=platform.machine())
        if not url.endswith(".tar.gz"):
            url = requests.get(url).text.strip()
        if install_package(
            url, self.folder, on_download=self.on_download, on_complete=self.on_complete
        ):
            raise TriggerReload
        return self.install_destination

    def install_model(self, url: str, wake_word: str) -> str:
        model_url = url.format(wake_word=wake_word)
        model_file = join(self.folder, posixpath.basename(model_url))
        try:
            install_package(
                model_url,
                self.folder,
                on_download=lambda: LOG.info("Updated precise model"),
            )
        except (HTTPError, ValueError):
            if isfile(model_file):
                LOG.info("Couldn't find remote model.  Using local file")
            else:
                raise NoModelAvailable("Failed to download model:", model_url)
        return model_file

    @staticmethod
    def _snd_msg(cmd):
        with suppress(OSError):
            with open("/dev/ttyAMA0", "w") as f:
                print(cmd, file=f)

    def on_download(self):
        LOG.info("Downloading Precise executable...")
        if isdir(join(self.folder, "precise-stream")):
            rmtree(join(self.folder, "precise-stream"))
        for old_package in glob(join(self.folder, "precise-engine_*.tar.gz")):
            os.remove(old_package)
        self.download_complete = False
        self.show_download_progress = Timer(5, self.during_download, args=[True])
        self.show_download_progress.start()

    def during_download(self, first_run=False):
        LOG.info("Still downloading executable...")
        if first_run:  # TODO: Localize
            self._snd_msg("mouth.text=Updating listener...")
        if not self.download_complete:
            self.show_download_progress = Timer(30, self.during_download)
            self.show_download_progress.start()

    def on_complete(self):
        LOG.info("Precise download complete!")
        self.download_complete = True
        self.show_download_progress.cancel()
        self._snd_msg("mouth.reset")

    def update(self, chunk):
        self.stream.write(chunk)

    def found_wake_word(self, frame_data):
        if self.has_found:
            self.has_found = False
            return True
        return False

    def stop(self):
        if self.runner:
            self.runner.stop()


class PorcupineHotWord(HotWordEngine):
    """Hotword engine using picovoice's Porcupine hot word engine.

    """

    def __init__(self, key_phrase="hey mycroft", config=None, lang="en-us"):
        super().__init__(key_phrase, config, lang)
        keyword_file_paths = [
            expanduser(x.strip())
            for x in self.config.get("keyword_file_path", "hey_mycroft.ppn").split(",")
        ]
        sensitivities = self.config.get("sensitivities", 0.5)
        access_key = self.config.get("access_key", "")

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

        LOG.info(
            "Loading Porcupine using library path {} and keyword paths {}".format(
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

        LOG.info("Loaded Porcupine")

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
                    self.audio_buffer[0:self.porcupine.frame_length]
                )
                # result will be the index of the found keyword or -1 if
                # nothing has been found.
                self.has_found |= result >= 0
                self.audio_buffer = self.audio_buffer[self.porcupine.frame_length:]
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
        "precise": PreciseHotword,
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
                    LOG.info("Loaded the Wake Word plugin {}".format(module))

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
            except PreciseUnavailable:
                LOG.warning(
                    "Settings prevent Precise Engine use, " "falling back to default."
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
            config = Configuration.get()["hotwords"]
        config = config.get(hotword) or config["hey mycroft"]

        module = config.get("module", "precise")
        return (
            cls.load_module(module, hotword, config, lang, loop)
            or cls.load_module("porcupine", hotword, config, lang, loop)
            or cls.CLASSES["porcupine"]()
        )
