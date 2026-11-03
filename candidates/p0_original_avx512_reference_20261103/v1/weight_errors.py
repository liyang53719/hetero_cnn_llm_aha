"""Finite public failure vocabulary. Never export transport detail."""
WEIGHT_FAILURE_REASONS = frozenset('WEIGHT_' + suffix for suffix in (
    'HTTP401', 'HTTP403', 'HTTP404', 'HTTP408', 'HTTP429', 'HTTP500',
    'HTTP502', 'HTTP503', 'HTTP504', 'HTTP_OTHER', 'REDIRECT_POLICY',
    'REDIRECT_LIMIT', 'RANGE_STATUS', 'RANGE_HEADER', 'RANGE_LENGTH',
    'ENCODING', 'BODY_SIZE', 'HEADER_HASH', 'HEADER_PREFIX', 'HEADER_JSON',
    'HEADER_GEOMETRY', 'TRANSPORT'))
