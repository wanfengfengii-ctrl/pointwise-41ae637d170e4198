from dataclasses import dataclass

from archive import array, fields, label
from recording.units import to_ticks


@dataclass(frozen=True)
class NormalizedRow:
    row_id: str
    marker: str
    reading: int
    position: str


@dataclass(frozen=True)
class Endpoint:
    value: int
    closed: bool


@dataclass(frozen=True)
class DifferenceConstraint:
    left: str
    right: str
    lower: Endpoint | None
    upper: Endpoint | None
    evidence: str


def normalize_endpoint(value, unit):
    if value is None:
        return None
    fields(value, 'value closed', 'endpoint')
    if type(value['closed']) is not bool:
        raise ValueError('endpoint closed flag must be a boolean')
    return Endpoint(to_ticks(value['value'], unit), value['closed'])


def normalize_rows(rows, unit):
    result = []
    for row in array(rows, 'recording rows'):
        fields(row, 'id marker reading position', 'recording row')
        result.append(NormalizedRow(label(row['id'], 'row ID'),
                                    label(row['marker'], 'marker'),
                                    to_ticks(row['reading'], unit),
                                    label(row['position'], 'source position')))
    if not result:
        raise ValueError('a recording must contain at least one row')
    return tuple(result)


def normalize_constraints(constraints, unit):
    result = []
    for relation in array(constraints, 'constraints'):
        fields(relation, 'from to lower upper evidence', 'difference constraint')
        result.append(DifferenceConstraint(
            label(relation['from'], 'from marker'), label(relation['to'], 'to marker'),
            normalize_endpoint(relation['lower'], unit),
            normalize_endpoint(relation['upper'], unit),
            label(relation['evidence'], 'evidence row'),
        ))
    return tuple(result)
