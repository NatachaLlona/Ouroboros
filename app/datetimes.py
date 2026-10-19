"""UTC canonical instants, validated source context and read-only presentation."""
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Annotated
import re
from pydantic import AfterValidator, AwareDatetime, BeforeValidator


def utcnow():
    """Return one aware UTC clock value for server timestamps."""
    return datetime.now(timezone.utc)


def from_timestamp(value):
    return datetime.fromtimestamp(value, timezone.utc)


def zone_name(value):
    """Validate an explicit IANA zone; never infer geography from an offset."""
    try:
        if not isinstance(value, str) or value.startswith(('/', '.')):
            raise ValueError
        ZoneInfo(value)
    except (ValueError, ZoneInfoNotFoundError):
        raise ValueError('Choose a valid IANA timezone') from None
    return value


def display_zone(value):
    return value if value == 'original' else zone_name(value)


def utc(value):
    """Normalize an aware instant without accepting ambiguous naive wall time."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('A UTC offset is required')
    return value.astimezone(timezone.utc)


def offset_instant(value):
    """Require an explicit ISO offset rather than coercing epoch numbers to UTC."""
    if isinstance(value, datetime):
        utc(value)
        return value
    if not isinstance(value, str) or not re.search(r'(?:Z|[+-]\d{2}:\d{2}(?::\d{2})?)$', value, re.IGNORECASE):
        raise ValueError('Supply an ISO 8601 datetime with an explicit UTC offset')
    return value


SourceInstant = Annotated[AwareDatetime, BeforeValidator(offset_instant)]
Instant = Annotated[SourceInstant, AfterValidator(utc)]
ZoneName = Annotated[str, AfterValidator(zone_name)]
DisplayZone = Annotated[str, AfterValidator(display_zone)]


def offset_text(value):
    """Keep the source offset of an aware input, including seconds if supplied."""
    seconds = int(value.utcoffset().total_seconds())
    sign = '+' if seconds >= 0 else '-'
    hours, rest = divmod(abs(seconds), 3600)
    minutes, seconds = divmod(rest, 60)
    return f'{sign}{hours:02d}:{minutes:02d}' + (f':{seconds:02d}' if seconds else '')


def source_values(value, supplied_zone=None):
    """Validate the supplied offset against an explicit IANA zone at that instant.

    Offset-aware instants disambiguate DST folds. Naive local times are rejected
    by the input schemas; nonexistent zone/offset combinations are rejected here.
    Returns canonical UTC, original offset, and explicit zone (or None).
    """
    if value is None:
        if supplied_zone is not None:
            raise ValueError('A source zone requires a completion instant')
        return None, None, None
    canonical = utc(value)
    if supplied_zone is not None:
        zone_name(supplied_zone)
        if canonical.astimezone(ZoneInfo(supplied_zone)).utcoffset() != value.utcoffset():
            raise ValueError('Timezone and supplied offset do not agree at this instant')
    return canonical, offset_text(value), supplied_zone


def check_range(start, end):
    """Validate inclusive-from/exclusive-to bounds after UTC normalization."""
    if start is not None and end is not None and start >= end:
        raise ValueError('The exclusive end must follow the inclusive start')


def fixed_zone(offset):
    """Build only an explicitly recorded numeric offset, never an inferred zone."""
    sign = 1 if offset[0] == '+' else -1
    parts = [int(part) for part in offset[1:].split(':')]
    return timezone(sign * timedelta(hours=parts[0], minutes=parts[1], seconds=parts[2] if len(parts) > 2 else 0))


def present(record, selection=None, default='Europe/Lisbon', source_zones=None):
    """Return canonical UTC values and a separate reproducible display object.

    Source context may be unknown for historical data, in which case original
    presentation explicitly falls back to UTC. Conversion uses each event's date.
    """
    result = dict(record)
    selected = display_zone(selection or default)
    dates = {}
    for field, value in list(result.items()):
        if isinstance(value, datetime):
            value = result[field] = utc(value)
            fallback = False
            name = selected
            if selected == 'original':
                name = result.get(field + '_timezone') or (source_zones or {}).get(field)
                offset = result.get(field + '_offset')
                if name:
                    target = ZoneInfo(name)
                elif offset:
                    name, target = offset, fixed_zone(offset)
                else:
                    name, target, fallback = 'UTC', timezone.utc, True
            else:
                target = ZoneInfo(selected)
            local = value.astimezone(target)
            dates[field] = dict(datetime=local.isoformat(), date=local.date().isoformat(),
                                time=local.time().isoformat(), timezone=name,
                                offset=offset_text(local), fallback_utc=fallback)
        elif field.endswith('_at') and value is None:
            dates[field] = None
    result['presentation'] = {'display_timezone': selected, 'dates': dates}
    return result
