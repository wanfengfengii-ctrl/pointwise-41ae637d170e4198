from dataclasses import dataclass

from archive import SqliteArchive, lookup_id
from intake.checks import CheckedPacket, check_packet


class ReceiptConflictError(ValueError):
    pass


@dataclass(frozen=True)
class ReceivedPacket:
    receipt_id: int
    packet: CheckedPacket

    @property
    def raw(self):
        return self.packet.raw


class ReceiptStore(SqliteArchive):
    def initialize(self):
        self.create_tables('''
            CREATE TABLE IF NOT EXISTS received_packets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                issue_id TEXT NOT NULL UNIQUE,
                raw BLOB NOT NULL
            )
        ''')

    def record(self, packet):
        with self.transaction() as db:
            stored = db.execute('SELECT id, raw FROM received_packets WHERE issue_id = ?',
                                (packet.issue_id,)).fetchone()
            if stored is not None:
                if stored[1] != packet.raw:
                    raise ReceiptConflictError(f'different original for issue {packet.issue_id}')
                receipt_id = stored[0]
            else:
                cursor = db.execute('INSERT INTO received_packets(issue_id, raw) VALUES (?, ?)',
                                    (packet.issue_id, packet.raw))
                receipt_id = cursor.lastrowid
        return ReceivedPacket(receipt_id, packet)

    def get(self, receipt_id):
        lookup_id(receipt_id, 'material receipt ID')
        with self.connection() as db:
            row = db.execute('SELECT raw FROM received_packets WHERE id = ?', (receipt_id,)).fetchone()
        if row is None:
            raise KeyError(receipt_id)
        return ReceivedPacket(receipt_id, check_packet(row[0]))
