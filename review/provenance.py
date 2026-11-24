from dataclasses import asdict, dataclass

from review.bounds import Bound
from review.constraints import Node


@dataclass(frozen=True)
class ReportOrigin:
    receipt_id: int
    issue_id: str
    batch: str
    station: str
    revision: int
    sha256: str


@dataclass(frozen=True)
class TracedEdge:
    origin: ReportOrigin
    relation_number: int
    side: str
    start: Node
    end: Node
    bound: Bound
    tickets: tuple[str, ...]

    def snapshot(self):
        return {'origin': asdict(self.origin), 'relation_number': self.relation_number,
                'side': self.side, 'start': list(self.start), 'end': list(self.end),
                'bound': self.bound.snapshot(), 'tickets': list(self.tickets)}

    @classmethod
    def from_snapshot(cls, item):
        return cls(ReportOrigin(**item['origin']), item['relation_number'], item['side'],
                   tuple(item['start']), tuple(item['end']), Bound.from_snapshot(item['bound']),
                   tuple(item['tickets']))


def build_report_origins(pair):
    return tuple(ReportOrigin(item.receipt_id, item.packet.issue_id, item.packet.batch,
                              item.packet.station, item.packet.revision, item.packet.sha256)
                 for item in pair.materials)


def _edge_tickets(packet, edge):
    if edge.side == 'condition':
        return packet.projection.conditions[edge.relation_number - 1].tickets
    if packet.version == 2:
        return packet.projection.relations[edge.relation_number - 1].tickets
    return packet.relations[edge.relation_number - 1].tickets


def trace_edges(pair, edges):
    origins = {item.receipt_id: item for item in build_report_origins(pair)}
    packets = {item.receipt_id: item.packet for item in pair.materials}
    return tuple(TracedEdge(origins[edge.receipt_id], edge.relation_number, edge.side,
                            edge.start, edge.end, edge.bound,
                            _edge_tickets(packets[edge.receipt_id], edge))
                 for edge in edges)


def trace_conflict(pair, closure):
    return trace_edges(pair, closure.conflict)
