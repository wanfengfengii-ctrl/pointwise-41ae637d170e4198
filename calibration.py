from dataclasses import dataclass
from fractions import Fraction

from archive import array, fields, label


@dataclass(frozen=True)
class Calibration:
    calibration_id: str
    lower: Fraction
    upper: Fraction

    def snapshot(self):
        return {'id': self.calibration_id,
                'range': [[self.lower.numerator, self.lower.denominator],
                          [self.upper.numerator, self.upper.denominator]]}


def _boundary(value):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError('calibration boundary must be [numerator, denominator]')
    numerator, denominator = value
    if type(numerator) is not int or type(denominator) is not int or denominator <= 0:
        raise ValueError('calibration boundary needs an integer numerator '
                         'and a positive integer denominator')
    return Fraction(numerator, denominator)


def parse_calibration(value):
    fields(value, 'id range', 'calibration')
    calibration_id = label(value['id'], 'calibration ID')
    bounds = array(value['range'], 'calibration range')
    if len(bounds) != 2:
        raise ValueError('calibration range must have exactly two boundaries')
    lower = _boundary(bounds[0])
    upper = _boundary(bounds[1])
    if lower > upper:
        raise ValueError('calibration range must be an ascending closed interval')
    return Calibration(calibration_id, lower, upper)


def parse_k(value):
    if type(value) is bool or not isinstance(value, (int, Fraction)):
        raise ValueError('k must be an integer or fractions.Fraction')
    return Fraction(value)
