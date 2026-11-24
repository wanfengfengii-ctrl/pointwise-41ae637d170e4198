from dataclasses import dataclass


@dataclass(frozen=True)
class SourceLocator:
    batch: str
    station: str
    revision_id: int
    row_id: str
    row_number: int
    position: str


def build_evidence_index(rows):
    index = {}
    for number, row in enumerate(rows, start=1):
        if row.row_id in index:
            raise ValueError(f'duplicate recording row: {row.row_id}')
        index[row.row_id] = (number, row.position)
    return index


def resolve_evidence(index, constraints):
    resolved = {}
    for relation in constraints:
        if relation.evidence not in index:
            raise ValueError(f'missing evidence in this recording: {relation.evidence}')
        resolved[relation.evidence] = index[relation.evidence]
    return resolved
