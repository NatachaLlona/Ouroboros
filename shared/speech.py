"""Bounded local speech transcription; audio and text never enter application logs."""
import io
import threading
import time
import os
from pathlib import Path

from shared.paths import ConfigurationError, PROJECT_ROOT


def transcription_settings(config):
    settings = config.setdefault('transcription', {})
    if not isinstance(settings, dict):
        raise ConfigurationError('transcription must be an object')
    from shared.assistance_settings import transcription_defaults
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


