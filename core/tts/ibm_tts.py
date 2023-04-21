from .tts import TTSValidator
from .remote_tts import RemoteTTS
from core.configuration import Configuration
from requests.auth import HTTPBasicAuth


class WatsonTTS(RemoteTTS):
    PARAMS = {'accept': 'audio/wav'}

    def __init__(self, lang, config,
                 url='https://stream.watsonplatform.net/text-to-speech/api',
                 api_path='/v1/synthesize'):
        super(WatsonTTS, self).__init__(lang, config, url, api_path,
                                        WatsonTTSValidator(self))
        self.type = "wav"
        user = self.config.get("user") or self.config.get("username")
        password = self.config.get("password")
        api_key = self.config.get("apikey")
        if self.url.endswith(api_path):
            self.url = self.url[:-len(api_path)]

        if api_key is None:
            self.auth = HTTPBasicAuth(user, password)
        else:
            self.auth = HTTPBasicAuth("apikey", api_key)

    def build_request_params(self, sentence):
        params = self.PARAMS.copy()
        params['LOCALE'] = self.lang
        params['voice'] = self.voice
        params['X-Watson-Learning-Opt-Out'] = self.config.get(
                                           'X-Watson-Learning-Opt-Out', 'true')
        params['text'] = sentence.encode('utf-8')
        return params


class WatsonTTSValidator(TTSValidator):
    def __init__(self, tts):
        super(WatsonTTSValidator, self).__init__(tts)

    def validate_lang(self):
        # TODO
        pass

    def validate_connection(self):
        config = Configuration.get().get("tts", {}).get("watson", {})
        user = config.get("user") or config.get("username")
        password = config.get("password")
        apikey = config.get("apikey")
        if user and password or apikey:
            return
        else:
            raise ValueError('user/pass or apikey for IBM tts is not defined')

    def get_tts_class(self):
        return WatsonTTS
