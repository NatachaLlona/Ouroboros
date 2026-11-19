"""Separate non-secret AI runtime limits, using the existing JSON configuration pattern."""
import json
import os
from pathlib import Path
from shared.paths import ConfigurationError, PROJECT_ROOT, ASSISTANCE_ROOT


def read_ai_document(path):
    try:
        document = json.loads(Path(path).read_text(encoding='utf-8'))
        if not isinstance(document, dict) or set(document)-{'transcription', 'form_assistant'} or not isinstance(document.get('transcription'), dict):
            raise ValueError
        return document
    except (OSError, ValueError, TypeError):
        raise ConfigurationError('Invalid AI configuration; expected a transcription JSON object') from None


def read_ai_config(path):
    return read_ai_document(path)['transcription']


def form_assistant_settings(settings=None):
    if settings is not None and not isinstance(settings, dict):
        raise ConfigurationError('Form assistant settings must be an object')
    defaults = read_ai_document(ASSISTANCE_ROOT / 'config.example.json')['form_assistant']
    settings = {**defaults, **(settings or {})}
    if set(settings) != set(defaults) or settings['model'] != 'gpt-5.4':
        raise ConfigurationError('The form assistant requires exclusively gpt-5.4 and known settings')
    for key, maximum in (('max_concurrency', 8), ('request_timeout_seconds', 300),
            ('connect_timeout_seconds', 60), ('max_output_tokens', 10000), ('max_response_bytes', 1048576)):
        if type(settings[key]) is not int or not 1 <= settings[key] <= maximum:
            raise ConfigurationError('Form assistant budgets must be bounded positive integers')
    return settings


def transcription_defaults():
    return read_ai_config(ASSISTANCE_ROOT / 'config.example.json')


