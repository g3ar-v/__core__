from ovos_plugin_manager.templates.stt import STT
from ovos_plugin_manager.stt import load_stt_plugin
from mycroft.api import STTApi, HTTPError
from mycroft.util.log import LOG
from mycroft.configuration import Configuration


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
