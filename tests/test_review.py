import json

from intake.store import ReceiptStore
from review.align import Conflict, review_pair
from review.bounds import Bound, DifferenceRange
from review.lookup import get_report
from review.reports import ReportStore, ReportWriteError, SignedReview
from tests import support


X = ('shared', 'X')
Y = ('shared', 'Y')


def independent_east(issue_id, second_step=1):
    return support.independent_packet(issue_id, 'east', [
        support.relation(X, ('local', 'U'), 'e1', upper=support.endpoint(1)),
        support.relation(('local', 'U'), Y, 'e2', upper=support.endpoint(second_step)),
    ], ['U'])


class ReviewTests(support.ArchiveCase):
    def review(self, east, west):
        return review_pair(self.receipts, self.reports, east, west, 'X', 'Y')

    def assert_closed_point(self, result, ids):
        self.assertIsInstance(result, SignedReview)
        self.assertEqual(result.report.interval, DifferenceRange(Bound(2, False), Bound(2, False)))
        self.assertEqual(tuple(origin.receipt_id for origin in result.report.origins), ids)
        self.assertEqual(result.receipt.material_ids, ids)

    def assert_conflict_cycle(self, result, ticket_keys):
        self.assertIsInstance(result, Conflict, 'ALIGNMENT_CONFLICT_REQUIRED')
        edges = result.witness
        self.assertTrue(edges)
        self.assertEqual([edge.end for edge in edges],
                         [edge.start for edge in edges[1:]] + [edges[0].start])
        total = sum(edge.bound.value for edge in edges)
        self.assertTrue(total < 0 or (total == 0 and any(edge.bound.strict for edge in edges)))
        self.assertEqual({(edge.origin.station, ticket) for edge in edges for ticket in edge.tickets},
                         ticket_keys)
        for edge in edges:
            material = self.receipts.get(edge.origin.receipt_id).packet
            self.assertEqual(edge.origin.issue_id, material.issue_id)
            self.assertEqual(edge.origin.sha256, material.sha256)
            relation = material.relations[edge.relation_number - 1]
            self.assertEqual(edge.tickets, relation.tickets)
            endpoint = relation.upper if edge.side == 'upper' else relation.lower
            value = endpoint.value if edge.side == 'upper' else -endpoint.value
            self.assertEqual(edge.bound, Bound(value, not endpoint.closed))

    def test_exact_point(self):
        east = self.receive(self.issue('east').raw)
        west = self.receive(self.issue('west').raw)
        self.close_sources()
        signed = self.review(east, west)
        self.assert_closed_point(signed, (east, west))
        self.assertEqual([edge.tickets for edge in signed.report.upper_witness], [('p1',), ('p2',)])
        self.assertEqual([edge.origin.receipt_id for edge in signed.report.lower_witness], [west])
        self.assertEqual(get_report(ReportStore(self.center), signed.report.report_id), signed)
        self.assert_success_counts(1)

    def test_explicit_receipt_and_order(self):
        west = self.receive(self.issue('west').raw)
        east = self.receive(self.issue('east').raw)
        later = support.sample('east.json')
        later['constraints'][1]['upper']['value'] = 2
        later_east = self.receive(self.issue('east', later).raw)
        self.close_sources()
        first = self.review(east, west)
        reversed_pair = self.review(west, east)
        self.assert_closed_point(first, (east, west))
        self.assert_closed_point(reversed_pair, (east, west))
        self.assertEqual(reversed_pair.report.origins, first.report.origins)
        self.assertEqual(reversed_pair.report.upper_witness, first.report.upper_witness)
        self.assertEqual(reversed_pair.report.lower_witness, first.report.lower_witness)
        new_pair = self.review(later_east, west)
        self.assertEqual(new_pair.report.interval, DifferenceRange(Bound(2, False), Bound(3, False)))
        self.assertEqual(new_pair.receipt.material_ids, (later_east, west))

    def test_strict_conflict(self):
        document = support.sample('west.json')
        document['constraints'][0]['lower']['closed'] = False
        east_packet = self.issue('east')
        west_packet = self.issue('west', document)
        east = self.receive(east_packet.raw)
        west = self.receive(west_packet.raw)
        expected_locations = {
            self.issues['east'].locate_origin(east_packet.issue_id, 'p1').row_id,
            self.issues['east'].locate_origin(east_packet.issue_id, 'p2').row_id,
            self.issues['west'].locate_origin(west_packet.issue_id, 'p1').row_id,
        }
        self.assertEqual(expected_locations, {'e1', 'e2', 'w1'})
        self.close_sources()
        rejected = self.review(east, west)
        self.assert_conflict_cycle(rejected, {('east', 'p1'), ('east', 'p2'), ('west', 'p1')})
        self.assertEqual(rejected, self.review(west, east))
        self.assertEqual([origin.receipt_id for origin in rejected.origins], [east, west])
        self.assert_success_counts(0)

    def test_independent_packets(self):
        east = self.receive(independent_east('east-two'))
        later = self.receive(independent_east('east-three', second_step=2))
        strict_raw = (support.SAMPLES / 'west-packet.json').read_bytes()
        west = self.receive(strict_raw)
        alternate = json.loads(strict_raw)['body']
        alternate['relations'][0]['lower']['closed'] = True
        closed_west = self.receive(support.fixed_packet('west-closed', alternate))
        self.close_sources()
        self.assert_conflict_cycle(self.review(east, west), {('east', 'e1'), ('east', 'e2'), ('west', 'w1')})
        self.assert_success_counts(0)
        expanded = self.review(later, west)
        self.assertEqual(expanded.report.interval, DifferenceRange(Bound(2, True), Bound(3, False)))
        self.assert_closed_point(self.review(east, closed_west), (east, closed_west))
        self.assert_success_counts(2)

    def test_strict_east(self):
        document = support.sample('east.json')
        document['constraints'][0]['upper']['closed'] = False
        east = self.receive(self.issue('east', document).raw)
        west = self.receive(self.issue('west').raw)
        self.close_sources()
        self.assert_conflict_cycle(self.review(east, west), {('east', 'p1'), ('east', 'p2'), ('west', 'p1')})
        self.assert_success_counts(0)

    def test_disconnected_conflict(self):
        west = self.receive(support.independent_packet('west-empty', 'west', []))
        for issue_id, backward in [('negative', support.endpoint(-1)), ('strict-zero', support.endpoint(0, False))]:
            east = self.receive(support.independent_packet(issue_id, 'east', [
                support.relation(('local', 'P'), ('local', 'Q'), 'out', upper=support.endpoint(0)),
                support.relation(('local', 'Q'), ('local', 'P'), 'back', upper=backward),
            ], ['P', 'Q']))
            self.assert_conflict_cycle(self.review(east, west), {('east', 'out'), ('east', 'back')})
        self.assert_success_counts(0)

    def test_local_names(self):
        local = ('local', 'U')
        receipts = []
        for station, offset in [('east', 1), ('west', 4)]:
            receipts.append(self.receive(support.independent_packet(f'{station}-namespace', station, [
                support.relation(X, local, 'local', lower=support.endpoint(offset), upper=support.endpoint(offset)),
                support.relation(X, Y, 'shared', lower=support.endpoint(2), upper=support.endpoint(2)),
            ], ['U'])))
        self.close_sources()
        forward = self.review(*receipts)
        reverse = self.review(*reversed(receipts))
        self.assert_closed_point(forward, tuple(receipts))
        self.assert_closed_point(reverse, tuple(receipts))
        self.assertEqual(forward.report.upper_witness, reverse.report.upper_witness)

    def test_unbounded(self):
        east = self.receive(support.independent_packet('east-empty', 'east', [
            support.relation(X, Y, 'unknown', lower=None, upper=None),
        ]))
        west = self.receive(support.independent_packet('west-empty', 'west', []))
        upper_only = self.receive(independent_east('east-upper'))
        self.close_sources()
        free = self.review(east, west).report
        self.assertEqual(free.interval, DifferenceRange(None, None))
        self.assertEqual((free.lower_witness, free.upper_witness), ((), ()))
        one_sided = self.review(upper_only, west).report
        self.assertEqual(one_sided.interval, DifferenceRange(None, Bound(2, False)))
        identity = review_pair(self.receipts, self.reports, east, west, 'X', 'X')
        self.assertEqual(identity.report.interval, DifferenceRange(Bound(0, False), Bound(0, False)))

    def test_invalid_pair(self):
        east = self.receive(self.issue('east').raw)
        same_station = self.receive(independent_east('another-east'))
        west = self.receive(self.issue('west').raw)
        foreign = self.receive(support.independent_packet('other-batch', 'west', [], batch='other'))
        document = json.loads((support.SAMPLES / 'west-packet.json').read_bytes())
        document['body']['anchors'][0]['meaning'] = 'different event'
        wrong_meaning = self.receive(support.fixed_packet('wrong-meaning', document['body']))
        for other in (same_station, foreign, wrong_meaning, east):
            with self.subTest(other=other):
                with self.assertRaises(ValueError):
                    self.review(east, other)
        with self.assertRaises(KeyError):
            self.review(east, 99999)
        with self.assertRaises(ValueError):
            review_pair(self.receipts, self.reports, east, west, 'X', 'unknown')
        self.assert_success_counts(0)

    def test_rollback_and_reopen(self):
        east_raw = self.issue('east').raw
        east = self.receive(east_raw)
        west = self.receive(self.issue('west').raw)
        newer = support.sample('east.json')
        newer['constraints'][1]['upper']['value'] = 2
        self.receive(self.issue('east', newer).raw)
        self.close_sources()
        old = self.review(east, west)
        with self.reports.transaction() as db:
            db.execute('''
                CREATE TRIGGER refuse_receipt BEFORE INSERT ON review_receipts
                WHEN EXISTS (SELECT 1 FROM reports WHERE id = NEW.report_id)
                BEGIN SELECT RAISE(ABORT, 'desk refused receipt after report insert'); END
            ''')
        with self.assertRaisesRegex(ReportWriteError, 'desk refused receipt after report insert'):
            self.review(east, west)
        self.assert_success_counts(1)
        self.reports = ReportStore(self.center)
        self.receipts = ReceiptStore(self.center)
        self.reports.initialize()
        self.receipts.initialize()
        self.assertEqual(get_report(self.reports, old.report.report_id), old)
        self.assertEqual(self.receipts.get(east).raw, east_raw)
        with self.assertRaises(KeyError):
            get_report(self.reports, old.report.report_id + 1)
        with self.assertRaisesRegex(ReportWriteError, 'desk refused receipt'):
            self.review(east, west)
        with self.reports.transaction() as db:
            db.execute('DROP TRIGGER refuse_receipt')
        new = self.review(west, east)
        self.assert_closed_point(new, (east, west))
        self.assert_success_counts(2)
        self.assertEqual(get_report(self.reports, old.report.report_id), old)
        self.assertEqual(get_report(self.reports, new.report.report_id), new)
