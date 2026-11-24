from dataclasses import dataclass
from hashlib import sha256

from archive import array, canonical_bytes, decode_json, fields, label, positive_id, unique_labels
from calibration import Calibration, parse_calibration
from issue.projection import Projection, ProjectionCondition, ProjectionRelation
from issue.relations import PacketRelation
from recording.normalize import normalize_affine_endpoint, normalize_endpoint
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
    version: int = 1
    calibration: Calibration | None = None
    projection: Projection | None = None


def _clock(value, declared):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError('invalid clock reference')
    scope = label(value[0], 'clock scope')
    name = label(value[1], 'clock identity')
    if scope not in declared or name not in declared[scope]:
        raise ValueError(f'undeclared clock: {scope}/{name}')
    return scope, name


def _shared_clock(value, anchors):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError('invalid clock reference')
    scope = label(value[0], 'clock scope')
    name = label(value[1], 'clock identity')
    if scope != 'shared' or name not in anchors:
        raise ValueError('projection endpoints must be declared shared anchors')
    return name


def _relation(item, declared, available_tickets):
    fields(item, 'left right lower upper tickets', 'packet relation')
    tickets = unique_labels(item['tickets'], 'relation origin tickets')
    if not tickets or not available_tickets.issuperset(tickets):
        raise ValueError('relation must reference declared origin tickets')
    return PacketRelation(_clock(item['left'], declared), _clock(item['right'], declared),
                          normalize_endpoint(item['lower'], 'ns'),
                          normalize_endpoint(item['upper'], 'ns'), tickets)


def _proof_tickets(value, available_tickets):
    tickets = unique_labels(value, 'projection origin tickets')
    if not tickets or not available_tickets.issuperset(tickets):
        raise ValueError('projection must reference declared origin tickets')
    return tickets


def _projection(value, anchors, available_tickets):
    fields(value, 'relations conditions', 'projection')
    relations = []
    for item in array(value['relations'], 'projection relations'):
        fields(item, 'left right bound tickets', 'projection relation')
        relations.append(ProjectionRelation(
            _shared_clock(item['left'], anchors), _shared_clock(item['right'], anchors),
            normalize_affine_endpoint(item['bound']),
            _proof_tickets(item['tickets'], available_tickets)))
    conditions = []
    for item in array(value['conditions'], 'projection conditions'):
        fields(item, 'bound tickets', 'projection condition')
        conditions.append(ProjectionCondition(
            normalize_affine_endpoint(item['bound']),
            _proof_tickets(item['tickets'], available_tickets)))
    return Projection(tuple(relations), tuple(conditions))


def _identity(body):
    batch = label(body['batch'], 'batch')
    station = label(body['station'], 'station')
    revision = positive_id(body['revision'], 'source revision ID')
    members = collect_stations(body['members'])
    if station not in members:
        raise ValueError('issuing station is not a declared member')
    anchors = collect_shared_anchors(body['anchors'])
    return batch, station, revision, members, anchors


def _read_v1(issue_id, digest, raw, body):
    body = fields(body, 'batch station revision members anchors auxiliary tickets relations',
                  'packet body')
    batch, station, revision, members, anchors = _identity(body)
    auxiliary = unique_labels(body['auxiliary'], 'auxiliary clocks')
    tickets = unique_labels(body['tickets'], 'origin tickets')
    declared = {'shared': {anchor.name for anchor in anchors}, 'local': set(auxiliary)}
    available_tickets = set(tickets)
    relations = tuple(_relation(item, declared, available_tickets)
                      for item in array(body['relations'], 'packet relations'))
    return CheckedPacket(issue_id, batch, station, revision, members, anchors,
                         auxiliary, tickets, relations, digest, raw)


def _read_v2(issue_id, digest, raw, body):
    body = fields(body, 'batch station revision members anchors calibration tickets projection',
                  'packet body')
    batch, station, revision, members, anchors = _identity(body)
    tickets = unique_labels(body['tickets'], 'origin tickets')
    calibration = parse_calibration(body['calibration'])
    projection = _projection(body['projection'], {anchor.name for anchor in anchors},
                             set(tickets))
    return CheckedPacket(issue_id, batch, station, revision, members, anchors,
                         (), tickets, (), digest, raw,
                         version=2, calibration=calibration, projection=projection)


def _read_packet(raw):
    if not isinstance(raw, bytes):
        raise ValueError('packet must be UTF-8 bytes')
    envelope = fields(decode_json(raw), 'version issue_id body sha256', 'packet envelope')
    version = envelope['version']
    if type(version) is not int or version not in (1, 2):
        raise ValueError('unsupported packet version')
    issue_id = label(envelope['issue_id'], 'issue ID')
    digest = label(envelope['sha256'], 'packet digest')
    protected = {'version': version, 'issue_id': issue_id, 'body': envelope['body']}
    if sha256(canonical_bytes(protected)).hexdigest() != digest:
        raise ValueError('packet digest mismatch')
    if version == 1:
        return _read_v1(issue_id, digest, raw, envelope['body'])
    return _read_v2(issue_id, digest, raw, envelope['body'])


def check_packet(raw):
    try:
        return _read_packet(raw)
    except (ValueError, RecursionError) as exc:
        raise PacketValidationError(str(exc)) from exc
