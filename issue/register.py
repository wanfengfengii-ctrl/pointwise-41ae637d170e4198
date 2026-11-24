from dataclasses import asdict
from uuid import uuid4

from archive import SqliteArchive, canonical_bytes, decode_json, label
from issue.origins import issue_origin_tickets
from issue.package import Packet, encode_calibrated_body, encode_packet_body, seal_packet
from issue.projection import project_revision
from issue.qualification import qualify_revision
from issue.relations import build_packet_relations
from recording.evidence import SourceLocator


class IssueRegister(SqliteArchive):
    def initialize(self):
        self.create_tables('''
            CREATE TABLE IF NOT EXISTS issues (
                issue_id TEXT PRIMARY KEY,
                raw BLOB NOT NULL
            )
        ''', '''
            CREATE TABLE IF NOT EXISTS issue_origins (
                issue_id TEXT NOT NULL REFERENCES issues(issue_id),
                ticket TEXT NOT NULL,
                source BLOB NOT NULL,
                PRIMARY KEY (issue_id, ticket)
            )
        ''')

    def record(self, packet, origins):
        with self.transaction() as db:
            db.execute('INSERT INTO issues(issue_id, raw) VALUES (?, ?)',
                       (packet.issue_id, packet.raw))
            db.executemany('INSERT INTO issue_origins(issue_id, ticket, source) VALUES (?, ?, ?)',
                           [(packet.issue_id, item.ticket, canonical_bytes(asdict(item.source)))
                            for item in origins])

    def get_packet(self, issue_id):
        label(issue_id, 'issue ID')
        with self.connection() as db:
            row = db.execute('SELECT raw FROM issues WHERE issue_id = ?', (issue_id,)).fetchone()
        if row is None:
            raise KeyError(issue_id)
        return Packet(issue_id, row[0])

    def locate_origin(self, issue_id, ticket):
        label(issue_id, 'issue ID')
        label(ticket, 'origin ticket')
        with self.connection() as db:
            row = db.execute('SELECT source FROM issue_origins WHERE issue_id = ? AND ticket = ?',
                             (issue_id, ticket)).fetchone()
        if row is None:
            raise KeyError((issue_id, ticket))
        return SourceLocator(**decode_json(row[0]))


def issue_packet(revisions, issues, batch, station, revision_id):
    qualified = qualify_revision(revisions, batch, station, revision_id)
    tickets = issue_origin_tickets(qualified)
    if qualified.revision.calibration is None:
        relations = build_packet_relations(qualified, tickets)
        packet = seal_packet(uuid4().hex, encode_packet_body(qualified, relations, tickets))
    else:
        projection = project_revision(qualified, tickets)
        packet = seal_packet(uuid4().hex,
                             encode_calibrated_body(qualified, projection, tickets), version=2)
    issues.record(packet, tickets)
    return packet
