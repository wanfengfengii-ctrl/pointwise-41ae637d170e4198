from dataclasses import dataclass

from calibration import parse_k
from intake.selection import select_pair
from review.bounds import Bound, to_difference_range
from review.constraints import ConstraintEdge, close_constraints
from review.provenance import ReportOrigin, TracedEdge, build_report_origins, trace_conflict, trace_edges


@dataclass(frozen=True)
class Conflict:
    batch: str
    x: str
    y: str
    origins: tuple[ReportOrigin, ReportOrigin]
    witness: tuple[TracedEdge, ...]


def _joint_clock(pair, material, clock):
    scope, name = clock
    if scope == 'shared':
        return scope, pair.batch, name
    return scope, str(material.receipt_id), name


def build_joint_edges(pair):
    edges = []
    for material in pair.materials:
        for number, relation in enumerate(material.packet.relations, start=1):
            left = _joint_clock(pair, material, relation.left)
            right = _joint_clock(pair, material, relation.right)
            if relation.upper is not None:
                bound = Bound(relation.upper.value, not relation.upper.closed)
                edges.append(ConstraintEdge(left, right, bound, material.receipt_id, number, 'upper'))
            if relation.lower is not None:
                bound = Bound(-relation.lower.value, not relation.lower.closed)
                edges.append(ConstraintEdge(right, left, bound, material.receipt_id, number, 'lower'))
    return tuple(edges)


def build_calibrated_edges(pair, k):
    edges = []
    for material in pair.materials:
        projection = material.packet.projection
        for number, relation in enumerate(projection.relations, start=1):
            left = ('shared', pair.batch, relation.left)
            right = ('shared', pair.batch, relation.right)
            bound = Bound(relation.bound.a + relation.bound.b * k, not relation.bound.closed)
            edges.append(ConstraintEdge(left, right, bound, material.receipt_id, number, 'upper'))
        zero = ('shared', pair.batch, pair.x)
        for number, condition in enumerate(projection.conditions, start=1):
            bound = Bound(condition.bound.a + condition.bound.b * k, not condition.bound.closed)
            edges.append(ConstraintEdge(zero, zero, bound, material.receipt_id, number, 'condition'))
    return tuple(edges)


def _review(pair, reports, edges, calibration_id=None, k=None):
    start = ('shared', pair.batch, pair.x)
    end = ('shared', pair.batch, pair.y)
    closure = close_constraints((start, end), edges)
    origins = build_report_origins(pair)
    if closure.conflict:
        return Conflict(pair.batch, pair.x, pair.y, origins, trace_conflict(pair, closure))
    interval = to_difference_range(closure.bound(start, end), closure.bound(end, start))
    return reports.commit(batch=pair.batch, x=pair.x, y=pair.y, interval=interval, origins=origins,
                          lower_witness=trace_edges(pair, closure.witness(end, start)),
                          upper_witness=trace_edges(pair, closure.witness(start, end)),
                          calibration_id=calibration_id, k=k)


def review_pair(receipts, reports, first_id, second_id, x, y, k=None):
    pair = select_pair(receipts, first_id, second_id, x, y)
    versions = {material.packet.version for material in pair.materials}
    if k is None:
        if versions != {1}:
            raise ValueError('calibrated packets require an explicit calibration value k')
        return _review(pair, reports, build_joint_edges(pair))
    k = parse_k(k)
    if versions != {2}:
        raise ValueError('a calibration value k requires two calibrated (version 2) packets')
    specs = {material.packet.calibration for material in pair.materials}
    if len(specs) != 1:
        raise ValueError('packets declare different calibration ids or intervals')
    spec = next(iter(specs))
    if not spec.lower <= k <= spec.upper:
        raise ValueError('calibration value k lies outside the fixed interval')
    return _review(pair, reports, build_calibrated_edges(pair, k), spec.calibration_id, k)
