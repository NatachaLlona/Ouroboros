"""Strict module-local JSONC and operator-authorized installation limits."""
from pathlib import Path
from database.settings import ConfigurationError, exact, initialize, integer

ROOT = Path(__file__).resolve().parents[3]


def load(root=ROOT):
    settings = initialize(root/'modules/api/config.jsonc', root/'modules/api/config.example.jsonc')
    exact(settings, ('host','port','startup_timeout_seconds','connect_timeout_seconds',
                     'statement_timeout_ms','connection_acquire_timeout_seconds',
                     'max_connections','token','limits','tls'), 'API configuration')
    exact(settings['tls'], ('certificate_file','private_key_file','server_name'), 'tls')
    for field in ('certificate_file','private_key_file','server_name'):
        if type(settings['tls'][field]) is not str or not settings['tls'][field].strip():
            raise ConfigurationError('tls.'+field+' must be a nonempty string')
    import re
    if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?', settings['tls']['server_name']):
        raise ConfigurationError('tls.server_name must be a DNS hostname or IPv4 address')
    if settings['host'] != '127.0.0.1':
        raise ConfigurationError('API host must be 127.0.0.1')
    integer(settings['port'],6969,6969,'API port')
    for field,low,high in (('startup_timeout_seconds',10,3600),('connect_timeout_seconds',1,60),
                            ('statement_timeout_ms',100,60000),('connection_acquire_timeout_seconds',1,60),('max_connections',1,32)):
        integer(settings[field],low,high,field)
    exact(settings['token'], ('issuer','audience','clock_skew_seconds'), 'token')
    for field in ('issuer','audience'):
        if type(settings['token'][field]) is not str or not 1 <= len(settings['token'][field]) <= 128:
            raise ConfigurationError('token.'+field+' must be a nonempty bounded string')
    integer(settings['token']['clock_skew_seconds'],0,30,'clock_skew_seconds')
    exact(settings['limits'], ('request_bytes','batch_items','page_size','token_ttl_seconds'), 'limits')
    for name, limits in settings['limits'].items():
        exact(limits, ('minimum','maximum','value'), 'limits.'+name)
        ceiling = {'request_bytes':1048576,'batch_items':300,'page_size':100,'token_ttl_seconds':86400}[name]
        for field in limits:
            integer(limits[field],1,ceiling,'limits.'+name+'.'+field)
        if not limits['minimum'] <= limits['value'] <= limits['maximum']:
            raise ConfigurationError('limits.'+name+': value must be inside the configured range')
    return settings


def effective(settings, records):
    values = {name: bounds['value'] for name,bounds in settings['limits'].items()}
    for record in records:
        name = record['name']
        if name not in values:
            continue
        bounds = settings['limits'][name]
        low,high,value = record['minimum_value'],record['maximum_value'],record['current_value']
        if not (all(item.is_finite() and item == item.to_integral_value() for item in (low,high,value))
                and bounds['minimum'] <= low <= value <= high <= bounds['maximum']):
            raise ConfigurationError(f"{name}: permitted range is {bounds['minimum']}..{bounds['maximum']}")
        values[name] = int(value)
    return values
