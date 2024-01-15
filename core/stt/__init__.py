import time
from threading import Event
from typing import List

from .whisper import FasterWhisperSTT
from .base import STT

from core.util.log import LOG
from core.util.plugins import load_plugin
from core.configuration import Configuration


def load_stt_plugin(module_name):
    """Wrapper function for loading stt plugin.

    Args:
        module_name (str): System stt module name from config
    Returns:
        class: STT plugin class
    """
    return load_plugin("mycroft.plugin.stt", module_name)


class STTFactory:
    CLASSES = {
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
                LOG.info("LOADED THE STT PLUGIN {}".format(module))
            return clazz()
        except Exception:
            # The STT backend failed to start. Report it and fall back to
            # default.
            LOG.exception(
                "The selected STT backend could not be loaded, "
                "falling back to default..."
            )
