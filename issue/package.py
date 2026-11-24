from dataclasses import asdict, dataclass
from hashlib import sha256

from archive import canonical_bytes, label


@dataclass(frozen=True)
class Packet:
    issue_id: str
    raw: bytes


def encode_packet_body(qualified, relations, tickets):
    revision = qualified.revision
    auxiliary = {name for relation in relations for scope, name in (relation.left, relation.right)
                 if scope == 'local'}
    return {
        'batch': revision.batch.batch,
        'station': revision.station,
        'revision': revision.revision_id,
        'members': list(revision.batch.stations),
        'anchors': [asdict(anchor) for anchor in revision.batch.anchors],
        'auxiliary': sorted(auxiliary),
        'tickets': [ticket.ticket for ticket in tickets],
        'relations': [asdict(relation) for relation in relations],
    }


def seal_packet(issue_id, body):
    protected = {'version': 1, 'issue_id': label(issue_id, 'issue ID'), 'body': body}
    digest = sha256(canonical_bytes(protected)).hexdigest()
    return Packet(issue_id, canonical_bytes({**protected, 'sha256': digest}))
