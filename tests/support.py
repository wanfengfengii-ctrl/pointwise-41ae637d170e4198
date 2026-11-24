import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from intake.receive import receive_packet
from intake.store import ReceiptStore
from issue.register import IssueRegister, issue_packet
from recording.intake import freeze_recording
from recording.revisions import RevisionStore
from registry.batches import register_batch
from registry.history import BatchRegistry
from review.reports import ReportStore


SAMPLES = Path(__file__).resolve().parents[1] / 'samples'
BATCH = 'HC-17'


def sample(name):
    return json.loads((SAMPLES / name).read_text(encoding='utf-8'))


def endpoint(value, closed=True):
    return {'value': value, 'closed': closed}


def relation(left, right, ticket, *, lower=None, upper=None):
    return {'left': list(left), 'right': list(right), 'lower': lower, 'upper': upper,
            'tickets': [ticket]}


def fixed_packet(issue_id, body):
    protected = {'version': 1, 'issue_id': issue_id, 'body': body}
    wire = json.dumps(protected, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
    envelope = dict(protected, sha256=hashlib.sha256(wire).hexdigest())
    return json.dumps(envelope, ensure_ascii=False, indent=2).encode()


def independent_packet(issue_id, station, relations, auxiliary=(), batch=BATCH):
    declaration = sample('batch.json')
    tickets = list(dict.fromkeys(ticket for item in relations for ticket in item['tickets']))
    return fixed_packet(issue_id, {
        'batch': batch, 'station': station, 'revision': 7, 'members': declaration['stations'],
        'anchors': declaration['anchors'], 'auxiliary': list(auxiliary), 'tickets': tickets,
        'relations': relations,
    })


class ArchiveCase(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.site = self.root / 'stations'
        self.site.mkdir()
        self.registry = BatchRegistry(self.site / 'registry.sqlite')
        self.registry.initialize()
        self.batch = register_batch(self.registry, sample('batch.json'))
        self.revisions = {}
        self.issues = {}
        for station in self.batch.stations:
            self.revisions[station] = RevisionStore(self.site / f'{station}-source.sqlite')
            self.issues[station] = IssueRegister(self.site / f'{station}-issues.sqlite')
            self.revisions[station].initialize()
            self.issues[station].initialize()
        self.center = self.root / 'center.sqlite'
        self.receipts = ReceiptStore(self.center)
        self.reports = ReportStore(self.center)
        self.receipts.initialize()
        self.reports.initialize()

    def freeze(self, station, document=None):
        if document is None:
            document = sample(f'{station}.json')
        return freeze_recording(self.registry, self.revisions[station], BATCH, station, document)

    def issue(self, station, document=None):
        frozen = self.freeze(station, document)
        return issue_packet(self.revisions[station], self.issues[station], BATCH, station,
                            frozen.revision_id)

    def receive(self, raw):
        return receive_packet(self.receipts, raw).receipt_id

    def close_sources(self):
        self.site.rename(self.root / 'closed-stations')
        self.assertFalse(self.site.exists())

    def row_count(self, store, table):
        # Table names here come only from the test source.
        with store.connection() as db:
            return db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]

    def assert_success_counts(self, count):
        self.assertEqual(self.row_count(self.reports, 'reports'), count)
        self.assertEqual(self.row_count(self.reports, 'review_receipts'), count)
