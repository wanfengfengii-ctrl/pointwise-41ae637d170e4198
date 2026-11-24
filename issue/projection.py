"""Exact projection of a calibrated (V2) revision onto shared timestamps.

A V2 station packet publishes only conditional relations between shared
timestamps plus feasibility conditions, parameterized by the calibration
value k.  Station-internal timestamps are eliminated by Fourier-Motzkin
elimination for difference constraints: every internal clock is removed by
composing the affine bounds of the paths through it.  For every rational k
in the calibrated interval the published constraints and conditions admit
exactly the shared assignments that can be completed into a solution of the
station's original constraints at that k.

Bounds are affine functions a + b*k carried as (a, b, strict, tickets).
For each ordered pair of shared clocks and for the zero-conditions only the
lower envelope over the frozen interval is kept: a bound is redundant when
another derivable bound is at least as tight throughout the interval, so
dropping it changes no feasible assignment at any k in range.  Each kept
bound carries the union of the origin tickets of the derivation, which is
the public proof material the center may cite back.
"""
from dataclasses import dataclass

from recording.normalize import AffineEndpoint


@dataclass(frozen=True)
class ProjectionRelation:
    left: str
    right: str
    bound: AffineEndpoint
    tickets: tuple[str, ...]


@dataclass(frozen=True)
class ProjectionCondition:
    bound: AffineEndpoint
    tickets: tuple[str, ...]


@dataclass(frozen=True)
class Projection:
    relations: tuple[ProjectionRelation, ...]
    conditions: tuple[ProjectionCondition, ...]


def _dominates(g, f, lo, hi):
    """True when bound g is at least as tight as f everywhere on [lo, hi]."""
    ga, gb, gs, _ = g
    fa, fb, fs, _ = f
    g_lo, g_hi = ga + gb * lo, ga + gb * hi
    f_lo, f_hi = fa + fb * lo, fa + fb * hi
    if g_lo > f_lo or g_hi > f_hi:
        return False
    # Equal affine values only meet at an interval end (or everywhere); a
    # closed g cannot cover a strict f where their values coincide.
    if fs and not gs and (g_lo == f_lo or g_hi == f_hi):
        return False
    return True


def _reduce(funcs, lo, hi):
    unique = []
    seen = set()
    for func in funcs:
        if func[:3] not in seen:
            seen.add(func[:3])
            unique.append(func)
    return [f for f in unique
            if not any(g is not f and _dominates(g, f, lo, hi) for g in unique)]


def project_revision(qualified, tickets):
    revision = qualified.revision
    lo, hi = revision.calibration.lower, revision.calibration.upper
    by_row = {ticket.source.row_id: ticket.ticket for ticket in tickets}
    anchors = {binding.marker: binding.anchor for binding in revision.bindings}

    def clock(marker):
        anchor = anchors.get(marker)
        return ('shared', anchor) if anchor is not None else ('local', marker)

    edges = {}
    for relation in revision.constraints:
        left, right = clock(relation.left), clock(relation.right)
        ticket = by_row[relation.evidence]
        for endpoints in ((relation.upper, left, right, 1), (relation.lower, right, left, -1)):
            endpoint, start, end, sign = endpoints
            if endpoint is not None:
                key = (start, end)
                edges.setdefault(key, []).append(
                    (sign * endpoint.a, sign * endpoint.b, not endpoint.closed, (ticket,)))
    for key in list(edges):
        edges[key] = _reduce(edges[key], lo, hi)

    conditions = []
    internal = sorted({node for edge in edges for node in edge if node[0] == 'local'})
    for node in internal:
        conditions.extend(edges.pop((node, node), []))
        incoming = [(start, funcs) for (start, end), funcs in edges.items() if end == node]
        outgoing = [(end, funcs) for (start, end), funcs in edges.items() if start == node]
        for start, _ in incoming:
            edges.pop((start, node), None)
        for end, _ in outgoing:
            edges.pop((node, end), None)
        for start, in_funcs in incoming:
            for end, out_funcs in outgoing:
                combined = [(fa + ga, fb + gb, fs or gs, tuple(sorted(set(ft) | set(gt))))
                            for fa, fb, fs, ft in in_funcs
                            for ga, gb, gs, gt in out_funcs]
                key = (start, end)
                edges[key] = _reduce(edges.get(key, []) + combined, lo, hi)

    relations = []
    for (start, end), funcs in edges.items():
        for a, b, strict, tickets_ in funcs:
            if start == end:
                conditions.append((a, b, strict, tickets_))
            else:
                relations.append(ProjectionRelation(
                    start[1], end[1], AffineEndpoint(a, b, not strict), tickets_))
    conditions = _reduce(conditions, lo, hi)
    relations.sort(key=lambda item: (item.left, item.right, item.bound.a,
                                     item.bound.b, item.bound.closed))
    conditions.sort()
    return Projection(
        tuple(relations),
        tuple(ProjectionCondition(AffineEndpoint(a, b, not strict), tickets_)
              for a, b, strict, tickets_ in conditions),
    )
