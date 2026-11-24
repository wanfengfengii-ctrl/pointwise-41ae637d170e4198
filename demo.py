import json
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

from intake.receive import receive_packet
from intake.store import ReceiptStore
from issue.register import IssueRegister, issue_packet
from recording.intake import freeze_recording
from recording.revisions import RevisionStore
from registry.batches import register_batch
from registry.history import BatchRegistry
from review.align import Conflict, review_pair
from review.bounds import Bound, DifferenceRange
from review.lookup import get_report
from review.reports import ReportStore, SignedReview


SAMPLES = Path(__file__).resolve().parent / 'samples'


def read_sample(name):
    return json.loads((SAMPLES / name).read_text(encoding='utf-8'))


def handoff(site, registry, batch, station):
    revisions = RevisionStore(site / f'{station}-recordings.sqlite')
    issues = IssueRegister(site / f'{station}-issues.sqlite')
    revisions.initialize()
    issues.initialize()
    frozen = freeze_recording(registry, revisions, batch, station, read_sample(f'{station}.json'))
    packet = issue_packet(revisions, issues, batch, station, frozen.revision_id)
    return issues.get_packet(packet.issue_id).raw


def main():
    with TemporaryDirectory() as directory:
        root = Path(directory)
        site = root / 'stations'
        site.mkdir()
        registry = BatchRegistry(site / 'batches.sqlite')
        registry.initialize()
        batch = register_batch(registry, read_sample('batch.json')).batch
        east_raw = handoff(site, registry, batch, 'east')
        west_raw = handoff(site, registry, batch, 'west')
        site.rename(root / 'closed-stations')

        center = root / 'center.sqlite'
        receipts, reports = ReceiptStore(center), ReportStore(center)
        receipts.initialize()
        reports.initialize()
        east = receive_packet(receipts, east_raw)
        west = receive_packet(receipts, west_raw)
        signed = review_pair(receipts, reports, west.receipt_id, east.receipt_id, 'X', 'Y')
        expected_interval = DifferenceRange(Bound(2, False), Bound(2, False))
        assert isinstance(signed, SignedReview) and signed.report.interval == expected_interval
        expected_materials = (east.receipt_id, west.receipt_id)
        historical = get_report(ReportStore(center), signed.report.report_id)
        assert historical == signed and historical.receipt.material_ids == expected_materials
        assert [receipts.get(item).raw for item in expected_materials] == [east_raw, west_raw]
        scenario = {
            'case_id': 'v5',
            'input': {'batch': batch, 'query': ['X', 'Y'], 'east_upper_steps': [1, 1], 'west_lower': 2},
            'expected': asdict(expected_interval),
            'actual': asdict(signed.report.interval),
            'downstream_expected': {'material_ids': expected_materials, 'original_report_retrieved': True},
            'downstream_actual': {'material_ids': historical.receipt.material_ids,
                                  'original_report_retrieved': historical == signed},
            'code_paths': ['issue/relations.py', 'intake/selection.py', 'review/align.py',
                           'review/constraints.py', 'review/reports.py', 'review/lookup.py'],
            'oracle': 'Add the east upper bounds 1 + 1, then intersect with the west closed lower bound 2.',
        }
        print('POINTWISE_SCENARIO ' + json.dumps(scenario, sort_keys=True))

        strict_west = receive_packet(receipts, (SAMPLES / 'west-packet.json').read_bytes())
        rejected = review_pair(receipts, reports, east.receipt_id, strict_west.receipt_id, 'X', 'Y')
        assert isinstance(rejected, Conflict)
        actual_origins = sorted((edge.origin.station, edge.tickets[0]) for edge in rejected.witness)
        assert actual_origins == [('east', 'p1'), ('east', 'p2'), ('west', 'w1')]
        with reports.connection() as db:
            counts = [db.execute('SELECT COUNT(*) FROM reports').fetchone()[0],
                      db.execute('SELECT COUNT(*) FROM review_receipts').fetchone()[0]]
        assert counts == [1, 1]
        print('POINTWISE_SCENARIO ' + json.dumps({
            'case_id': 'v6.independent_packets',
            'input': {'batch': batch, 'query': ['X', 'Y'], 'east_upper_steps': [1, 1],
                      'west_lower': {'value': 2, 'closed': False}},
            'expected': 'conflict', 'actual': 'conflict' if isinstance(rejected, Conflict) else 'signed',
            'downstream_expected': {'totals': [1, 1], 'tickets': [('east', 'p1'), ('east', 'p2'), ('west', 'w1')]},
            'downstream_actual': {'totals': counts, 'tickets': actual_origins},
            'code_paths': ['intake/checks.py', 'review/align.py', 'review/constraints.py', 'review/provenance.py'],
            'oracle': 'A value cannot simultaneously be at most 1 + 1 and strictly greater than 2.',
        }, sort_keys=True))


if __name__ == '__main__':
    main()
