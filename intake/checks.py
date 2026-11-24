from dataclasses import dataclass
from hashlib import sha256

from archive import array, canonical_bytes, decode_json, fields, label, positive_id, unique_labels
from issue.relations import PacketRelation
from recording.normalize import normalize_endpoint
from registry.anchors import SharedAnchor, collect_shared_anchors
from registry.bindings import collect_stations


class PacketValidationError(ValueError):
    pass


@dataclass(frozen=True)
class CheckedPacket:
    issue_id: str
    batch: str
    station: str
    revision: int
    members: tuple[str, str]
    anchors: tuple[SharedAnchor, ...]
    auxiliary: tuple[str, ...]
    tickets: tuple[str, ...]
    relations: tuple[PacketRelation, ...]
    sha256: str
    raw: bytes


def _clock(value, declared):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError('invalid clock reference')
    scope = label(value[0], 'clock scope')
    name = label(value[1], 'clock identity')
    if scope not in declared or name not in declared[scope]:
        raise ValueError(f'undeclared clock: {scope}/{name}')
    return scope, name


def _relation(item, declared, available_tickets):
    fields(item, 'left right lower upper tickets', 'packet relation')
    tickets = unique_labels(item['tickets'], 'relation origin tickets')
    if not tickets or not available_tickets.issuperset(tickets):
        raise ValueError('relation must reference declared origin tickets')
    return PacketRelation(_clock(item['left'], declared), _clock(item['right'], declared),
                          normalize_endpoint(item['lower'], 'ns'),
                          normalize_endpoint(item['upper'], 'ns'), tickets)


def _read_packet(raw):
    if not isinstance(raw, bytes):
        raise ValueError('packet must be UTF-8 bytes')
    envelope = fields(decode_json(raw), 'version issue_id body sha256', 'packet envelope')
    if type(envelope['version']) is not int or envelope['version'] != 1:
        raise ValueError('unsupported packet version')
    issue_id = label(envelope['issue_id'], 'issue ID')
    digest = label(envelope['sha256'], 'packet digest')
    protected = {'version': 1, 'issue_id': issue_id, 'body': envelope['body']}
    if sha256(canonical_bytes(protected)).hexdigest() != digest:
        raise ValueError('packet digest mismatch')
    body = fields(envelope['body'], 'batch station revision members anchors auxiliary tickets relations',
                  'packet body')
    batch = label(body['batch'], 'batch')
    station = label(body['station'], 'station')
    revision = positive_id(body['revision'], 'source revision ID')
    members = collect_stations(body['members'])
    if station not in members:
        raise ValueError('issuing station is not a declared member')
    anchors = collect_shared_anchors(body['anchors'])
    auxiliary = unique_labels(body['auxiliary'], 'auxiliary clocks')
    tickets = unique_labels(body['tickets'], 'origin tickets')
    declared = {'shared': {anchor.name for anchor in anchors}, 'local': set(auxiliary)}
    available_tickets = set(tickets)
    relations = tuple(_relation(item, declared, available_tickets)
                      for item in array(body['relations'], 'packet relations'))
    return CheckedPacket(issue_id, batch, station, revision, members, anchors,
                         auxiliary, tickets, relations, digest, raw)


def check_packet(raw):
    try:
        return _read_packet(raw)
    except (ValueError, RecursionError) as exc:
        raise PacketValidationError(str(exc)) from exc
