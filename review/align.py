from dataclasses import dataclass

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


def review_pair(receipts, reports, first_id, second_id, x, y):
    pair = select_pair(receipts, first_id, second_id, x, y)
    start = ('shared', pair.batch, pair.x)
    end = ('shared', pair.batch, pair.y)
    closure = close_constraints((start, end), build_joint_edges(pair))
    origins = build_report_origins(pair)
    if closure.conflict:
        return Conflict(pair.batch, pair.x, pair.y, origins, trace_conflict(pair, closure))
    interval = to_difference_range(closure.bound(start, end), closure.bound(end, start))
    return reports.commit(batch=pair.batch, x=pair.x, y=pair.y, interval=interval, origins=origins,
                          lower_witness=trace_edges(pair, closure.witness(end, start)),
                          upper_witness=trace_edges(pair, closure.witness(start, end)))
