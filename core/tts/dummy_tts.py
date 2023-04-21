"""A Dummy TTS without any audio output."""

from core.util.log import LOG

from .tts import TTS, TTSValidator


class DummyTTS(TTS):
    def __init__(self, lang, config):
        super().__init__(lang, config, DummyValidator(self), 'wav')

    def execute(self, sentence, ident=None, listen=False):
        """Don't do anything, return nothing."""
        LOG.info('Mycroft: {}'.format(sentence))
        self.end_audio(listen)
        return None


class DummyValidator(TTSValidator):
    """Do no tests."""
    def __init__(self, tts):
        super().__init__(tts)

    def validate_lang(self):
        pass

    def validate_connection(self):
        pass

    def get_tts_class(self):
        return DummyTTS
