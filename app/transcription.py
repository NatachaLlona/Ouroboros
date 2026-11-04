"""Bounded local speech transcription; audio and text never enter application logs."""
import io
import threading
import time
import os
from pathlib import Path

from app.config import ConfigurationError, PROJECT_ROOT


def transcription_settings(config):
    settings = config.setdefault('transcription', {})
    if not isinstance(settings, dict):
        raise ConfigurationError('transcription must be an object')
    from app.ai_config import transcription_defaults
    defaults = transcription_defaults()
    for key, value in defaults.items():
        settings.setdefault(key, value)
    for key in ('model', 'device', 'compute_type', 'cache_directory'):
        if not isinstance(settings[key], str) or not settings[key].strip():
            raise ConfigurationError('transcription presentation-independent runtime settings must be nonblank strings')
    for key, maximum in (('max_audio_bytes', 268435456), ('max_duration_seconds', 3600), ('max_concurrency', 4), ('cpu_threads', 16),
            ('duration_tolerance_ms', 2000), ('upload_timeout_seconds', 600), ('processing_timeout_seconds', 7200),
            ('request_timeout_seconds', 8400), ('max_transcript_chars', 1000000), ('segment_seconds', 30),
            ('recording_chunk_ms', 2000), ('audio_bits_per_second', 256000)):
        if type(settings[key]) is not int or not 1 <= settings[key] <= maximum:
            raise ConfigurationError('transcription limits must be positive bounded integers')
    if settings['request_timeout_seconds'] <= settings['upload_timeout_seconds'] + settings['processing_timeout_seconds']:
        raise ConfigurationError('transcription request timeout must exceed upload and processing budgets')
    languages = settings['idiomas_transcricao']
    if not isinstance(languages, list) or not languages or any(not isinstance(value, str) or not value.isascii() or not value.isalpha() or not 2 <= len(value) <= 3 or value != value.lower() for value in languages):
        raise ConfigurationError('transcription.idiomas_transcricao must contain lowercase language codes')
    if type(settings['local_files_only']) is not bool:
        raise ConfigurationError('transcription.local_files_only must be boolean')
    return settings


class SpeechError(Exception):
    def __init__(self, code, stage='', cause=None):
        super().__init__('Local transcription could not be completed')
        self.code = code
        self.stage = stage
        self.cause_type = type(cause).__name__ if cause is not None else ''
        self.missing_module = cause.name if isinstance(cause, ModuleNotFoundError) else None

    def diagnostic(self):
        """Only structural failure metadata, never exception messages or media content."""
        return {'error_code': self.code, 'stage': self.stage, 'exception_type': self.cause_type,
                'missing_module': self.missing_module}


class LocalTranscription:
    """One lazy model per application process, with bounded decoding and inference."""
    def __init__(self, config):
        self.settings = transcription_settings(config)
        self._model = None
        self._model_lock = threading.Lock()
        self._slots = threading.BoundedSemaphore(self.settings['max_concurrency'])

    def acquire(self):
        return self._slots.acquire(blocking=False)

    def release(self):
        self._slots.release()

    @property
    def cache_path(self):
        cache = Path(os.environ.get('OUROBOROS_SPEECH_CACHE', self.settings['cache_directory']))
        return (cache if cache.is_absolute() else PROJECT_ROOT / cache).resolve()

    def model(self):
        with self._model_lock:
            if self._model is None:
                try:
                    from faster_whisper import WhisperModel
                except Exception as error:
                    raise SpeechError('TRANSCRIPTION_UNAVAILABLE', 'model_dependencies', error) from error
                cache = self.cache_path
                try:
                    cache.mkdir(parents=True, exist_ok=True)
                except OSError as error:
                    raise SpeechError('TRANSCRIPTION_UNAVAILABLE', 'cache_directory', error) from error
                try:
                    model = WhisperModel(self.settings['model'], device=self.settings['device'],
                        compute_type=self.settings['compute_type'], download_root=str(cache),
                        local_files_only=self.settings['local_files_only'], cpu_threads=self.settings['cpu_threads'],
                        num_workers=self.settings['max_concurrency'], use_auth_token=False)
                    if not model.model.is_multilingual:
                        raise SpeechError('TRANSCRIPTION_UNAVAILABLE')
                    self._model = model
                except Exception as error:
                    raise SpeechError('TRANSCRIPTION_UNAVAILABLE', 'model_load', error) from error
        return self._model

    def close(self):
        with self._model_lock:
            self._model = None

    def transcribe(self, data, cancelled=None):
        deadline = time.monotonic() + self.settings['processing_timeout_seconds']
        def check_progress():
            if cancelled is not None and cancelled.is_set():
                raise SpeechError('REQUEST_CANCELLED')
            if time.monotonic() > deadline:
                raise SpeechError('TRANSCRIPTION_TIMEOUT')
        check_progress()
        try:
            import av
            import numpy as np
        except (ImportError, OSError) as error:
            raise SpeechError('TRANSCRIPTION_UNAVAILABLE', 'audio_dependencies', error) from error
        # Force an approved demuxer; never let uploaded playlists open external resources.
        if data[:4] == b'\x1aE\xdf\xa3':
            container_format = 'matroska'
        elif data[:4] == b'OggS':
            container_format = 'ogg'
        elif len(data) > 12 and data[4:8] == b'ftyp':
            container_format = 'mov'
        elif data[:4] == b'RIFF' and data[8:12] == b'WAVE':
            container_format = 'wav'
        else:
            raise SpeechError('AUDIO_INVALID')
        # Decode only the permitted duration. Do not trust MIME, filename or container metadata.
        maximum = int((self.settings['max_duration_seconds'] + self.settings['duration_tolerance_ms'] / 1000) * 16000)
        chunks, samples = [], 0
        try:
            with av.open(io.BytesIO(data), mode='r', format=container_format, options={'protocol_whitelist': ''}) as container:
                if not container.streams.audio:
                    raise SpeechError('AUDIO_INVALID')
                stream = container.streams.audio[0]
                resampler = av.AudioResampler(format='fltp', layout='mono', rate=16000)
                for frame in container.decode(stream):
                    check_progress()
                    if not 1000 <= frame.sample_rate <= 192000 or len(frame.layout.channels) > 8:
                        raise SpeechError('AUDIO_INVALID')
                    for converted in resampler.resample(frame):
                        samples += converted.samples
                        if samples > maximum:
                            raise SpeechError('AUDIO_LIMIT_EXCEEDED')
                        chunks.append(converted.to_ndarray().reshape(-1))
                for converted in resampler.resample(None):
                    samples += converted.samples
                    if samples > maximum:
                        raise SpeechError('AUDIO_LIMIT_EXCEEDED')
                    chunks.append(converted.to_ndarray().reshape(-1))
        except SpeechError:
            raise
        except Exception:
            raise SpeechError('AUDIO_INVALID') from None
        if samples < 1600:
            raise SpeechError('AUDIO_INVALID')
        audio = np.concatenate(chunks).astype(np.float32)
        if not np.isfinite(audio).all() or float(np.max(np.abs(audio))) < 0.0001:
            raise SpeechError('AUDIO_INVALID')
        try:
            check_progress()
            # faster-whisper advances across the complete waveform in native windows.
            # Keep pauses in the waveform; do not delete intervals using a pre-VAD pass.
            segments, info = self.model().transcribe(audio, language=None, beam_size=3,
                condition_on_previous_text=False, vad_filter=False, chunk_length=self.settings['segment_seconds'], log_progress=False)
            if info.language not in self.settings['idiomas_transcricao']:
                raise SpeechError('TRANSCRIPTION_LANGUAGE_REJECTED')
            parts, characters, last_start = [], 0, -1.0
            for segment in segments:
                check_progress()
                if segment.start < last_start:
                    raise SpeechError('TRANSCRIPTION_UNAVAILABLE', 'segment_order')
                last_start = segment.start
                characters += len(segment.text)
                if characters > self.settings['max_transcript_chars']:
                    raise SpeechError('AUDIO_LIMIT_EXCEEDED')
                parts.append(segment.text)
            check_progress()
            text = ''.join(parts).strip()
            if not text:
                raise SpeechError('AUDIO_INVALID')
            return {'text': text, 'language': info.language, 'complete': True, 'duration_seconds': samples / 16000}
        except SpeechError:
            raise
        except Exception as error:
            raise SpeechError('TRANSCRIPTION_UNAVAILABLE', 'inference', error) from None
