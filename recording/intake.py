from archive import fields, label
from recording.evidence import build_evidence_index, resolve_evidence
from recording.normalize import normalize_constraints, normalize_rows
from registry.bindings import resolve_revision_bindings


def freeze_recording(registry, revisions, batch, station, document):
    fields(document, 'unit rows constraints', 'recording')
    snapshot = registry.get_snapshot(batch)
    label(station, 'recording station')
    if station not in snapshot.stations:
        raise ValueError('recording station is not a member of this batch')
    unit = document['unit']
    rows = normalize_rows(document['rows'], unit)
    constraints = normalize_constraints(document['constraints'], unit)
    markers = {row.marker for row in rows}
    for relation in constraints:
        if relation.left not in markers or relation.right not in markers:
            raise ValueError('relation refers to a marker absent from this recording')
    bindings = resolve_revision_bindings(snapshot, station, markers)
    evidence = resolve_evidence(build_evidence_index(rows), constraints)
    return revisions.save(snapshot, station, rows, constraints, bindings, evidence)
