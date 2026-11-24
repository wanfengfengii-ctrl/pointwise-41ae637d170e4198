from dataclasses import asdict, dataclass

from archive import SqliteArchive, canonical_bytes, decode_json, lookup_id
from recording.evidence import SourceLocator
from recording.normalize import DifferenceConstraint, NormalizedRow, normalize_endpoint
from registry.bindings import MarkerBinding
from registry.history import RegisteredBatch


@dataclass(frozen=True)
class FrozenRevision:
    revision_id: int
    batch: RegisteredBatch
    station: str
    rows: tuple[NormalizedRow, ...]
    constraints: tuple[DifferenceConstraint, ...]
    bindings: tuple[MarkerBinding, ...]
    locations: tuple[SourceLocator, ...]


def _restore(revision_id, payload):
    batch = RegisteredBatch.from_snapshot(payload['batch'])
    station = payload['station']
    constraints = tuple(
        DifferenceConstraint(item['left'], item['right'],
                             normalize_endpoint(item['lower'], 'ns'),
                             normalize_endpoint(item['upper'], 'ns'), item['evidence'])
        for item in payload['constraints']
    )
    locations = tuple(SourceLocator(batch.batch, station, revision_id, row_id, number, position)
                      for row_id, number, position in payload['locations'])
    return FrozenRevision(revision_id, batch, station,
                          tuple(NormalizedRow(**row) for row in payload['rows']), constraints,
                          tuple(MarkerBinding(**binding) for binding in payload['bindings']),
                          locations)


class RevisionStore(SqliteArchive):
    def initialize(self):
        self.create_tables('''
            CREATE TABLE IF NOT EXISTS revisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot BLOB NOT NULL
            )
        ''')

    def save(self, batch, station, rows, constraints, bindings, evidence):
        payload = {
            'batch': asdict(batch),
            'station': station,
            'rows': [asdict(row) for row in rows],
            'constraints': [asdict(relation) for relation in constraints],
            'bindings': [asdict(binding) for binding in bindings],
            'locations': [(row_id, number, position)
                          for row_id, (number, position) in evidence.items()],
        }
        with self.transaction() as db:
            cursor = db.execute('INSERT INTO revisions(snapshot) VALUES (?)',
                                (canonical_bytes(payload),))
            revision = _restore(cursor.lastrowid, payload)
        return revision

    def get(self, revision_id):
        lookup_id(revision_id, 'revision ID')
        with self.connection() as db:
            row = db.execute('SELECT snapshot FROM revisions WHERE id = ?', (revision_id,)).fetchone()
        if row is None:
            raise KeyError(revision_id)
        return _restore(revision_id, decode_json(row[0]))
