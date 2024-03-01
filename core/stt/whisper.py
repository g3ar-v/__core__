import numpy as np
import torch
import whisper
from speech_recognition import AudioData

from core.util.log import LOG

from .base import STT


class WhisperSTT(STT):
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
            model = "base.en"
        assert model in self.MODELS  # TODO - better error handling

        LOG.info(f"whisper model: {model}")
        self.engine = whisper.load_model(model)
        self.transcription = [""]

    @staticmethod
    def audiodata2array(audio_data):
        # Convert buffer to float32 using NumPy
        audio_as_np_int16 = np.frombuffer(audio_data, dtype=np.int16)
        audio_as_np_float32 = audio_as_np_int16.astype(np.float32)

        # Normalise float32 array so that values are between -1.0 and +1.0
        max_int16 = 2**15
        data = audio_as_np_float32 / max_int16
        return data

    def execute(self, audio: AudioData, language=None):
        result = self.engine.transcribe(
            self.audiodata2array(audio.get_raw_data()),
        )
        text = result["text"].strip()
        self.transcription.append(text)
        self.transcription[-1] = text
        return self.transcription

    def stream_start(self):
        self.streaming = True
        LOG.info("TRANSCRIPTION STARTED")

    def stream_stop(self):
        self.streaming = False
        LOG.info("FINISHED TRANSCRIPTION")
        return self.transcription

    def stream_data(self, audio_chunk: bytes):
        try:
            # LOG.info("transcribing.....")
            result = self.engine.transcribe(
                self.audiodata2array(audio_chunk),
                fp16=torch.cuda.is_available(),
            )
            text = result["text"].strip()
            LOG.info("results from whisper: %s", text)
            self.transcription.append(text)
        except Exception as e:
            LOG.error(f"error in realtime transcription: {e}")
