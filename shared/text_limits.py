"""Application-owned description limits and deterministic Unicode segmentation."""
import json
from pathlib import Path

import uniseg
from uniseg.graphemecluster import grapheme_clusters
from pydantic_core import PydanticCustomError

TEXT_LIMITS = json.loads(Path(__file__).with_suffix('.json').read_text(encoding='utf-8'))
DESCRIPTION_MAX_LENGTH = TEXT_LIMITS['description_max_length']
GRAPHEME_UNICODE_VERSION = TEXT_LIMITS['grapheme_unicode_version']
if type(DESCRIPTION_MAX_LENGTH) is not int or DESCRIPTION_MAX_LENGTH < 1:
    raise ValueError('Invalid application description limit')
if uniseg.unidata_version != GRAPHEME_UNICODE_VERSION:
    raise ValueError('Description segmentation Unicode version mismatch')


def description_length(value: str) -> int:
    """Count extended grapheme clusters, without trimming or normalization."""
    return sum(1 for _ in grapheme_clusters(value))


def validate_description(value: str) -> str:
    """Reject over-limit input; never truncate or rewrite persisted descriptions."""
    for index, _ in enumerate(grapheme_clusters(value), 1):
        if index > DESCRIPTION_MAX_LENGTH:
            raise PydanticCustomError('description_too_long',
                'Description must contain at most {max_length} Unicode grapheme clusters',
                {'max_length': DESCRIPTION_MAX_LENGTH})
    return value


DESCRIPTION_INPUT_HELP = (
    f'Optional description; at most {DESCRIPTION_MAX_LENGTH} extended grapheme clusters '
    f'(Unicode {GRAPHEME_UNICODE_VERSION}, UAX #29). Spaces and composed emojis count. '
    'Omit on PUT to preserve; null clears. Over-limit input returns VALIDATION_ERROR; never truncated.'
)
