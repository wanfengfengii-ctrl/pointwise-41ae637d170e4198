from dataclasses import dataclass

from archive import label
from intake.store import ReceivedPacket


@dataclass(frozen=True)
class SelectedPair:
    batch: str
    x: str
    y: str
    materials: tuple[ReceivedPacket, ReceivedPacket]


def select_pair(receipts, first_id, second_id, x, y):
    label(x, 'first query anchor')
    label(y, 'second query anchor')
    first = receipts.get(first_id)
    second = receipts.get(second_id)
    a, b = first.packet, second.packet
    if a.batch != b.batch or a.members != b.members or a.anchors != b.anchors:
        raise ValueError('selected materials do not share a fixed batch declaration')
    if a.station == b.station:
        raise ValueError('joint review requires one receipt from each station')
    declared = {anchor.name for anchor in a.anchors}
    if x not in declared or y not in declared:
        raise ValueError('both query anchors must be declared by the batch')
    materials = tuple(sorted((first, second), key=lambda item: item.packet.station))
    return SelectedPair(a.batch, x, y, materials)
