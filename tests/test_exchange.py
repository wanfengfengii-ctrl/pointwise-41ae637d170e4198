import json
import sqlite3

from intake.checks import PacketValidationError, check_packet
from intake.store import ReceiptConflictError, ReceiptStore
from issue.register import IssueRegister, issue_packet
from tests import support


class ExchangeTests(support.ArchiveCase):
    def test_immutable_receipt(self):
        packet = self.issue('east')
        first = self.receive(packet.raw)
        self.assertEqual(self.receive(packet.raw), first)
        self.issue('east')
        self.assertEqual(IssueRegister(self.issues['east'].path).get_packet(packet.issue_id), packet)
        reopened = ReceiptStore(self.center)
        reopened.initialize()
        saved = reopened.get(first)
        self.assertEqual(saved.raw, packet.raw)
        self.assertEqual(saved.packet.issue_id, packet.issue_id)
        self.assertEqual(self.row_count(reopened, 'received_packets'), 1)

    def test_same_id_different_content(self):
        original = (support.SAMPLES / 'west-packet.json').read_bytes()
        document = json.loads(original)
        first = self.receive(original)
        document['body']['relations'][0]['lower']['value'] = 3
        replacement = support.fixed_packet(document['issue_id'], document['body'])
        self.assertEqual(check_packet(replacement).issue_id, document['issue_id'])
        with self.assertRaises(ReceiptConflictError):
            self.receive(replacement)
        self.assertEqual(self.receive(original), first)
        self.assertEqual(ReceiptStore(self.center).get(first).raw, original)
        self.assertEqual(self.row_count(self.receipts, 'received_packets'), 1)

    def test_bad_packet(self):
        original = self.issue('east')
        damaged = json.loads(original.raw)
        damaged['body']['relations'][0]['upper']['value'] += 1
        with self.assertRaisesRegex(PacketValidationError, 'digest mismatch'):
            self.receive(json.dumps(damaged).encode())
        self.assertEqual(self.row_count(self.receipts, 'received_packets'), 0)
        self.assertEqual(self.receipts.get(self.receive(original.raw)).raw, original.raw)

    def test_bad_envelope(self):
        raw = self.issue('east').raw
        for malformed in (b'\xff', b'{"version":1,"version":1}', b'[]', raw + b'!'):
            with self.subTest(malformed=malformed):
                with self.assertRaises(PacketValidationError):
                    self.receive(malformed)
        self.assertEqual(self.row_count(self.receipts, 'received_packets'), 0)

    def test_invalid_relation_reference(self):
        packet = self.issue('east')
        for key, value in [('right', ['local', 'absent']), ('left', ['shared', 'absent']),
                           ('tickets', ['absent']), ('upper', {'value': 1, 'closed': 'yes'})]:
            with self.subTest(key=key):
                document = json.loads(packet.raw)
                document['body']['relations'][0][key] = value
                raw = support.fixed_packet(document['issue_id'], document['body'])
                with self.assertRaises(PacketValidationError):
                    self.receive(raw)
        self.assertEqual(self.row_count(self.receipts, 'received_packets'), 0)

    def test_issue_revision_and_joint_facts(self):
        first = self.freeze('east')
        document = support.sample('east.json')
        document['constraints'][1]['upper']['value'] = 2
        document['rows'][2]['position'] = 'redo:18'
        second = self.freeze('east', document)
        revisions, issues = self.revisions['east'], self.issues['east']
        for revision, step, position in [(first, 1, 'trace-A:3'), (second, 2, 'redo:18')]:
            with self.subTest(revision=revision.revision_id):
                packet = issue_packet(revisions, issues, support.BATCH, 'east', revision.revision_id)
                receipt_id = self.receive(packet.raw)
                self.assertEqual(self.receive(packet.raw), receipt_id)
                stored = self.receipts.get(receipt_id).packet
                self.assertEqual(stored.revision, revision.revision_id)
                one, two = stored.relations
                self.assertEqual(one.left, ('shared', 'X'))
                self.assertEqual(one.right[0], 'local')
                self.assertEqual(one.right, two.left)
                self.assertEqual(two.right, ('shared', 'Y'))
                self.assertEqual((one.upper.value, two.upper.value), (1, step))
                self.assertTrue(one.upper.closed and two.upper.closed)
                self.assertEqual(issues.locate_origin(packet.issue_id, one.tickets[0]), revision.locations[0])
                locator = IssueRegister(issues.path).locate_origin(packet.issue_id, two.tickets[0])
                self.assertEqual((locator.row_id, locator.row_number, locator.position), ('e2', 3, position))
                self.assertEqual(locator.revision_id, revision.revision_id)
                self.assertNotIn(b'cam-start', packet.raw)
                self.assertNotIn(b'cam-peak', packet.raw)
                self.assertNotIn(b'trace-A', packet.raw)
                self.assertNotIn(b'"U"', packet.raw)
        self.assertEqual(self.row_count(self.receipts, 'received_packets'), 2)

    def test_foreign_revision(self):
        revision = self.freeze('east')
        store, issues = self.revisions['east'], self.issues['east']
        for batch, station in [('another-batch', 'east'), (support.BATCH, 'west')]:
            with self.subTest(batch=batch, station=station):
                with self.assertRaises(ValueError):
                    issue_packet(store, issues, batch, station, revision.revision_id)
        with self.assertRaises(KeyError):
            issue_packet(store, issues, support.BATCH, 'east', revision.revision_id + 1)
        self.assertEqual(self.row_count(issues, 'issues'), 0)

    def test_issue_rollback(self):
        old = self.issue('east')
        issues = self.issues['east']
        with issues.transaction() as db:
            db.execute('''CREATE TRIGGER reject_origin BEFORE INSERT ON issue_origins
                          BEGIN SELECT RAISE(ABORT, 'origin archive closed'); END''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'origin archive closed'):
            self.issue('east')
        self.assertEqual(self.row_count(issues, 'issues'), 1)
        self.assertEqual(self.row_count(issues, 'issue_origins'), 2)
        self.assertEqual(issues.get_packet(old.issue_id), old)
