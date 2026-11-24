from dataclasses import dataclass


@dataclass(frozen=True)
class Bound:
    value: int
    strict: bool


@dataclass(frozen=True)
class DifferenceRange:
    lower: Bound | None
    upper: Bound | None

    @classmethod
    def from_snapshot(cls, snapshot):
        lower = snapshot['lower']
        upper = snapshot['upper']
        return cls(Bound(**lower) if lower is not None else None,
                   Bound(**upper) if upper is not None else None)


def add_bounds(left, right):
    return Bound(left.value + right.value, left.strict or right.strict)


def tighter_bound(candidate, current):
    return current is None or (candidate.value, not candidate.strict) < (current.value, not current.strict)


def to_difference_range(forward, backward):
    lower = None if backward is None else Bound(-backward.value, backward.strict)
    return DifferenceRange(lower, forward)
