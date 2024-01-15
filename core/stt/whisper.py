import numpy as np
import torch
import whisper
from faster_whisper import WhisperModel
from speech_recognition import AudioData

from core.util.log import LOG

from .base import STT


class FasterWhisperSTT(STT):
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
            model = "large-v2"
        assert model in self.MODELS  # TODO - better error handling

        self.streaming = False
        self.beam_size = self.config.get("beam_size", 5)
        self.compute_type = self.config.get("compute_type", "int8")
        self.use_cuda = self.config.get("use_cuda", False)
        self.cpu_threads = self.config.get("cpu_threads", 4)

        if self.use_cuda:
            device = "cuda"
        else:
            device = "cpu"
        self.fast_engine = WhisperModel(
            "large-v2",
            device=device,
            compute_type=self.compute_type,
            cpu_threads=self.cpu_threads,
        )
        LOG.info("whisper model: %s", model)
        # TODO: create a blocker for whisper loading
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
        # lang = language or self.lang
        # segments, _ = self.fast_engine.transcribe(
        #     self.audiodata2array(audio),
        #     beam_size=self.beam_size,
        #     condition_on_previous_text=False,
        #     language=lang.split("-")[0].lower(),
        # )
        # # segments is an iterator, transcription only happens here
        # transcription = ""
        # for segment in segments:
        #     transcription = segment.text
        # return transcription

        result = self.engine.transcribe(
            self.audiodata2array(audio.get_raw_data()),
            fp16=torch.cuda.is_available(),
        )
        # segments, _ = self.engine.transcribe(
        #     self.audiodata2array(audio),
        #     beam_size=self.beam_size,
        #     condition_on_previous_text=False,
        # )
        # LOG.info(f"result of all text: {result}")
        text = result["text"].strip()
        # for segment in segments:
        #     text = segment.text
        # LOG.info("results from whipser: %s", text)
        # self.transcription.append(text)
        self.transcription[-1] = text
        # LOG.info("results from faster whipser: %s", self.transcription)
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
