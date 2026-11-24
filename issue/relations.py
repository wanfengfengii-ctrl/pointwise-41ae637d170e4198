from dataclasses import dataclass

from recording.normalize import Endpoint


Clock = tuple[str, str]


@dataclass(frozen=True)
class PacketRelation:
    left: Clock
    right: Clock
    lower: Endpoint | None
    upper: Endpoint | None
    tickets: tuple[str, ...]


def build_packet_relations(qualified, tickets):
    revision = qualified.revision
    clocks = {binding.marker: ('shared', binding.anchor) for binding in revision.bindings}
    anonymous = 0
    for row in revision.rows:
        if row.marker not in clocks:
            anonymous += 1
            clocks[row.marker] = ('local', f'a{anonymous}')
    by_row = {ticket.source.row_id: ticket.ticket for ticket in tickets}
    return tuple(PacketRelation(clocks[relation.left], clocks[relation.right],
                                relation.lower, relation.upper, (by_row[relation.evidence],))
                 for relation in revision.constraints)
