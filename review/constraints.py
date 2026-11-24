from dataclasses import dataclass

from review.bounds import Bound, add_bounds, tighter_bound


Node = tuple[str, str, str]


@dataclass(frozen=True)
class ConstraintEdge:
    start: Node
    end: Node
    bound: Bound
    receipt_id: int
    relation_number: int
    side: str


@dataclass(frozen=True)
class _Path:
    bound: Bound
    edges: tuple[ConstraintEdge, ...]


@dataclass
class ConstraintClosure:
    _paths: dict[tuple[Node, Node], _Path]
    conflict: tuple[ConstraintEdge, ...]

    def bound(self, start, end):
        path = self._paths.get((start, end))
        return None if path is None else path.bound

    def witness(self, start, end):
        path = self._paths.get((start, end))
        return () if path is None else path.edges


def close_constraints(vertices, edges):
    edges = tuple(edges)
    nodes = set(vertices)
    for edge in edges:
        nodes.update((edge.start, edge.end))
    nodes = sorted(nodes)
    zero = _Path(Bound(0, False), ())
    paths = {(node, node): zero for node in nodes}

    def offer(start, end, bound, head, tail=()):
        previous = paths.get((start, end))
        if not tighter_bound(bound, None if previous is None else previous.bound):
            return ()
        witness = head + tail
        if start == end:
            return witness
        paths[start, end] = _Path(bound, witness)
        return ()

    for edge in edges:
        conflict = offer(edge.start, edge.end, edge.bound, (edge,))
        if conflict:
            return ConstraintClosure({}, conflict)

    for pivot in nodes:
        # With a feasible diagonal, paths to and from the pivot stay fixed in this step.
        incoming = [(node, paths[node, pivot]) for node in nodes if (node, pivot) in paths]
        outgoing = [(node, paths[pivot, node]) for node in nodes if (pivot, node) in paths]
        for start, head in incoming:
            for end, tail in outgoing:
                bound = add_bounds(head.bound, tail.bound)
                conflict = offer(start, end, bound, head.edges, tail.edges)
                if conflict:
                    return ConstraintClosure({}, conflict)
    return ConstraintClosure(paths, ())
