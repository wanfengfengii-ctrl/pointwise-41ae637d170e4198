from dataclasses import asdict, dataclass

from archive import SqliteArchive, canonical_bytes, decode_json, label
from registry.anchors import SharedAnchor
from registry.bindings import MarkerBinding


@dataclass(frozen=True)
class RegisteredBatch:
    batch: str
    stations: tuple[str, str]
    anchors: tuple[SharedAnchor, ...]
    bindings: tuple[MarkerBinding, ...]

    @classmethod
    def from_snapshot(cls, snapshot):
        return cls(snapshot['batch'], tuple(snapshot['stations']),
                   tuple(SharedAnchor(**anchor) for anchor in snapshot['anchors']),
                   tuple(MarkerBinding(**binding) for binding in snapshot['bindings']))


class BatchRegistry(SqliteArchive):
    def initialize(self):
        self.create_tables('''
            CREATE TABLE IF NOT EXISTS batches (
                batch TEXT PRIMARY KEY,
                snapshot BLOB NOT NULL
            )
        ''')

    def save_snapshot(self, snapshot):
        raw = canonical_bytes(asdict(snapshot))
        with self.transaction() as db:
            stored = db.execute('SELECT snapshot FROM batches WHERE batch = ?',
                                (snapshot.batch,)).fetchone()
            if stored is None:
                db.execute('INSERT INTO batches(batch, snapshot) VALUES (?, ?)',
                           (snapshot.batch, raw))
            else:
                previous = RegisteredBatch.from_snapshot(decode_json(stored[0]))
                if previous != snapshot:
                    raise ValueError(f'batch {snapshot.batch} already has a different declaration')
                return previous
        return snapshot

    def get_snapshot(self, batch):
        label(batch, 'batch')
        with self.connection() as db:
            row = db.execute('SELECT snapshot FROM batches WHERE batch = ?', (batch,)).fetchone()
        if row is None:
            raise KeyError(batch)
        return RegisteredBatch.from_snapshot(decode_json(row[0]))
