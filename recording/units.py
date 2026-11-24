from types import MappingProxyType


UNIT_SCALE = MappingProxyType({'ns': 1, 'us': 1000, 'ms': 1000000, 's': 1000000000})


def to_ticks(value, unit):
    if not isinstance(unit, str) or unit not in UNIT_SCALE:
        raise ValueError(f'unsupported time unit: {unit!r}')
    if type(value) is not int:
        raise ValueError('time values must be integers')
    return value * UNIT_SCALE[unit]
