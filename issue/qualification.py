from dataclasses import dataclass

from archive import label
from recording.revisions import FrozenRevision


@dataclass(frozen=True)
class QualifiedRevision:
    revision: FrozenRevision


def qualify_revision(revisions, batch, station, revision_id):
    label(batch, 'issue batch')
    label(station, 'issue station')
    revision = revisions.get(revision_id)
    if revision.batch.batch != batch or revision.station != station:
        raise ValueError('the frozen revision belongs to another batch or station')
    if station not in revision.batch.stations or not revision.batch.anchors:
        raise ValueError('the frozen revision has no eligible batch declaration')
    return QualifiedRevision(revision)
