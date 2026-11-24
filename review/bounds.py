from dataclasses import dataclass
from fractions import Fraction


@dataclass(frozen=True)
class Bound:
    value: int | Fraction
    strict: bool

    def snapshot(self):
        value = self.value
        if isinstance(value, Fraction):
            value = [value.numerator, value.denominator]
        return {'value': value, 'strict': self.strict}

    @classmethod
    def from_snapshot(cls, item):
        value = item['value']
        if isinstance(value, list):
            value = Fraction(value[0], value[1])
        return cls(value, item['strict'])


@dataclass(frozen=True)
class DifferenceRange:
    lower: Bound | None
    upper: Bound | None

    def snapshot(self):
        return {'lower': None if self.lower is None else self.lower.snapshot(),
                'upper': None if self.upper is None else self.upper.snapshot()}

    @classmethod
    def from_snapshot(cls, snapshot):
        lower = snapshot['lower']
        upper = snapshot['upper']
        return cls(Bound.from_snapshot(lower) if lower is not None else None,
                   Bound.from_snapshot(upper) if upper is not None else None)


def add_bounds(left, right):
    return Bound(left.value + right.value, left.strict or right.strict)


def tighter_bound(candidate, current):
    return current is None or (candidate.value, not candidate.strict) < (current.value, not current.strict)


def to_difference_range(forward, backward):
    lower = None if backward is None else Bound(-backward.value, backward.strict)
    return DifferenceRange(lower, forward)
