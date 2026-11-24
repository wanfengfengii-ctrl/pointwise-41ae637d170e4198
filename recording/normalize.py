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
class AffineEndpoint:
    a: int
    b: int
    closed: bool


@dataclass(frozen=True)
class DifferenceConstraint:
    left: str
    right: str
    lower: Endpoint | AffineEndpoint | None
    upper: Endpoint | AffineEndpoint | None
    evidence: str


def normalize_endpoint(value, unit):
    if value is None:
        return None
    fields(value, 'value closed', 'endpoint')
    if type(value['closed']) is not bool:
        raise ValueError('endpoint closed flag must be a boolean')
    return Endpoint(to_ticks(value['value'], unit), value['closed'])


def normalize_affine_endpoint(value):
    if value is None:
        return None
    fields(value, 'a b closed', 'affine endpoint')
    if type(value['a']) is not int or type(value['b']) is not int:
        raise ValueError('affine endpoint coefficients must be integers')
    if type(value['closed']) is not bool:
        raise ValueError('endpoint closed flag must be a boolean')
    return AffineEndpoint(value['a'], value['b'], value['closed'])


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


def normalize_constraints(constraints, unit, affine=False):
    result = []
    for relation in array(constraints, 'constraints'):
        fields(relation, 'from to lower upper evidence', 'difference constraint')
        if affine:
            lower = normalize_affine_endpoint(relation['lower'])
            upper = normalize_affine_endpoint(relation['upper'])
        else:
            lower = normalize_endpoint(relation['lower'], unit)
            upper = normalize_endpoint(relation['upper'], unit)
        result.append(DifferenceConstraint(
            label(relation['from'], 'from marker'), label(relation['to'], 'to marker'),
            lower, upper,
            label(relation['evidence'], 'evidence row'),
        ))
    return tuple(result)
