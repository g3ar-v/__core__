from openai import OpenAI

from core import LOG
from core.configuration import Configuration

from .tts import TTS, TTSValidator


class OpenAITTS(TTS):
    def __init__(self, lang, config):
        super(OpenAITTS, self).__init__(lang, config, OpenAITTSValidator(self))
        self.config = Configuration.get().get("tts", {}).get("openai", {})
        self.api_key = self.config.get("api_key")
        self.client = OpenAI(api_key=self.api_key)

    def get_tts(self, sentence, wav_file):
        response = self.client.audio.speech.create(
            model=self.config.get("model", {}),
            voice=self.config.get("voice", {}),
            input=sentence,
        )
        # audio = response.choices[0].message["content"]
        response.stream_to_file(wav_file)
        # Path(wav_file).write_bytes(audio)
        # LOG.info(wav_file)
        return (wav_file, None)


class OpenAITTSValidator(TTSValidator):
    def __init__(self, tts):
        super(OpenAITTSValidator, self).__init__(tts)

    def validate_lang(self):
        # Assuming OpenAI API supports the language set in Mycroft
        return True

    def validate_connection(self):
        # Assuming the API key is correct
        return True

    def get_tts_class(self):
        return OpenAITTS
