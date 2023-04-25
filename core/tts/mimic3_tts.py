# Copyright 2022 Mycroft AI Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import io
import logging
import re
import typing
import wave
from pathlib import Path

from core.messagebus.message import Message
from core.tts.cache import AudioFile
from core.util.log import LOG

from .tts import TTS, TTSValidator

from mimic3_tts import (
    AudioResult,
    Mimic3Settings,
    Mimic3TextToSpeechSystem,
    SSMLSpeaker,
)


class Mimic3(TTS):
    """Mycroft interface to Mimic3."""

    def __init__(self, lang, config):
        self.lang = lang

        voice: typing.Optional[str] = config.get("voice")
        preload_voices: typing.Optional[typing.List[str]] = config.get("preload_voices")

        self.tts = Mimic3TextToSpeechSystem(
            Mimic3Settings(
                voice=config.get("voice"),
                language=config.get("language"),
                voices_directories=config.get("voices_directories"),
                voices_url_format=config.get("voices_url_format"),
                speaker=config.get("speaker"),
                length_scale=config.get("length_scale"),
                noise_scale=config.get("noise_scale"),
                noise_w=config.get("noise_w"),
                voices_download_dir=config.get("voices_download_dir"),
                use_deterministic_compute=config.get(
                    "use_deterministic_compute", False
                ),
            )
        )

        super(Mimic3, self).__init__(lang, config, Mimic3Validator(self), "wav")

        if voice:
            self.tts.preload_voice(voice)

        if preload_voices:
            for voice in preload_voices:
                self.tts.preload_voice(voice)

        preloaded_cache = config.get("preloaded_cache")
        if preloaded_cache:
            self.persistent_cache_dir = Path(preloaded_cache)
            self.persistent_cache_dir.mkdir(parents=True, exist_ok=True)
            self._load_existing_audio_files()

    def get_tts(self, sentence, wav_file):
        """Synthesize audio using Mimic3 on device"""

        sentence, ssml = self._apply_text_hacks(sentence)
        wav_bytes = self._synthesize(sentence, ssml=ssml)

        # Write WAV to file
        Path(wav_file).write_bytes(wav_bytes)

        return (wav_file, None)

    def _apply_text_hacks(self, sentence: str) -> typing.Tuple[str, bool]:
        """Mycroft-specific workarounds for text.

        Returns: (text, ssml)
        """

        # HACK: Mycroft gives "eight a.m.next sentence" sometimes
        sentence = sentence.replace(" a.m.", " a.m. ")
        sentence = sentence.replace(" p.m.", " p.m. ")

        # A I -> A.I.
        sentence = re.sub(
            r"\b([A-Z](?: |$)){2,}",
            lambda m: m.group(0).strip().replace(" ", ".") + ". ",
            sentence,
        )

        # Assume SSML if sentence begins with an angle bracket
        ssml = sentence.strip().startswith("<")

        # HACK: Speak single letters from Mycroft (e.g., "A;")
        if (len(sentence) == 2) and sentence.endswith(";"):
            letter = sentence[0]
            ssml = True
            sentence = f'<say-as interpret-as="spell-out">{letter}</say-as>'
        else:
            # HACK: 'A' -> spell out
            sentence, subs_made = re.subn(
                r"'([A-Z])'",
                r'<say-as interpret-as="spell-out">\1</say-as>',
                sentence,
            )
            if subs_made > 0:
                ssml = True

        return (sentence, ssml)

    def _synthesize(self, text: str, ssml: bool = False) -> bytes:
        """Synthesize audio from text and return WAV bytes"""
        with io.BytesIO() as wav_io:
            wav_file: wave.Wave_write = wave.open(wav_io, "wb")
            wav_params_set = False

            with wav_file:
                try:
                    if ssml:
                        # SSML
                        results = SSMLSpeaker(self.tts).speak(text)
                    else:
                        # Plain text
                        self.tts.begin_utterance()
                        self.tts.speak_text(text)
                        results = self.tts.end_utterance()

                    for result in results:
                        # Add audio to existing WAV file
                        if isinstance(result, AudioResult):
                            if not wav_params_set:
                                wav_file.setframerate(result.sample_rate_hz)
                                wav_file.setsampwidth(result.sample_width_bytes)
                                wav_file.setnchannels(result.num_channels)
                                wav_params_set = True

                            wav_file.writeframes(result.audio_bytes)
                except Exception as e:
                    if not wav_params_set:
                        # Set default parameters so exception can propagate
                        wav_file.setframerate(22050)
                        wav_file.setsampwidth(2)
                        wav_file.setnchannels(1)

                    raise e

            wav_bytes = wav_io.getvalue()

        return wav_bytes

    def _load_existing_audio_files(self):
        """Find the TTS audio files already in the persistent cache."""
        glob_pattern = "*." + self.audio_ext
        for file_path in self.persistent_cache_dir.glob(glob_pattern):
            sentence_hash = file_path.name.split(".")[0]
            audio_file = AudioFile(
                self.persistent_cache_dir, sentence_hash, self.audio_ext
            )
            self.cache.cached_sentences[sentence_hash] = audio_file, None


class Mimic3Validator(TTSValidator):
    """Mycroft TTS validator for Mimic 3"""

    def __init__(self, tts):
        super(Mimic3Validator, self).__init__(tts)

    def validate_lang(self):
        # TODO: Check against model language
        pass

    def validate_connection(self):
        pass

    def get_tts_class(self):
        return Mimic3
