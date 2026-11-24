import sqlite3
from dataclasses import asdict, dataclass
from fractions import Fraction

from archive import SqliteArchive, canonical_bytes, decode_json, lookup_id
from review.bounds import DifferenceRange
from review.provenance import ReportOrigin, TracedEdge


class ReportWriteError(RuntimeError):
    pass


@dataclass(frozen=True)
class Report:
    report_id: int
    batch: str
    x: str
    y: str
    interval: DifferenceRange
    origins: tuple[ReportOrigin, ReportOrigin]
    lower_witness: tuple[TracedEdge, ...]
    upper_witness: tuple[TracedEdge, ...]
    calibration_id: str | None = None
    k: Fraction | None = None


@dataclass(frozen=True)
class ReviewReceipt:
    success_id: str
    report_id: int
    material_ids: tuple[int, int]


@dataclass(frozen=True)
class SignedReview:
    report: Report
    receipt: ReviewReceipt


class ReportStore(SqliteArchive):
    def initialize(self):
        self.create_tables('''
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot BLOB NOT NULL
            )
        ''', '''
            CREATE TABLE IF NOT EXISTS review_receipts (
                report_id INTEGER PRIMARY KEY REFERENCES reports(id),
                snapshot BLOB NOT NULL
            )
        ''')

    def commit(self, *, batch, x, y, interval, origins, lower_witness, upper_witness,
               calibration_id=None, k=None):
        payload = {
            'batch': batch, 'x': x, 'y': y, 'interval': interval.snapshot(),
            'origins': [asdict(origin) for origin in origins],
            'lower_witness': [edge.snapshot() for edge in lower_witness],
            'upper_witness': [edge.snapshot() for edge in upper_witness],
            'calibration_id': calibration_id,
            'k': None if k is None else [k.numerator, k.denominator],
        }
        materials = tuple(origin.receipt_id for origin in origins)
        try:
            with self.transaction() as db:
                cursor = db.execute('INSERT INTO reports(snapshot) VALUES (?)',
                                    (canonical_bytes(payload),))
                report_id = cursor.lastrowid
                receipt = ReviewReceipt(f'R{report_id}', report_id, materials)
                db.execute('INSERT INTO review_receipts(report_id, snapshot) VALUES (?, ?)',
                           (report_id, canonical_bytes(asdict(receipt))))
        except sqlite3.Error as exc:
            raise ReportWriteError(f'joint report could not be committed: {exc}') from exc
        return SignedReview(Report(report_id, batch, x, y, interval, origins,
                                   lower_witness, upper_witness, calibration_id, k), receipt)

    def load(self, report_id):
        lookup_id(report_id, 'report ID')
        with self.connection() as db:
            row = db.execute('''
                SELECT reports.snapshot, review_receipts.snapshot FROM reports
                JOIN review_receipts ON reports.id = review_receipts.report_id
                WHERE reports.id = ?
            ''', (report_id,)).fetchone()
        if row is None:
            raise KeyError(report_id)
        payload, receipt = map(decode_json, row)
        k = payload.get('k')
        report = Report(
            report_id, payload['batch'], payload['x'], payload['y'],
            DifferenceRange.from_snapshot(payload['interval']),
            tuple(ReportOrigin(**origin) for origin in payload['origins']),
            tuple(TracedEdge.from_snapshot(edge) for edge in payload['lower_witness']),
            tuple(TracedEdge.from_snapshot(edge) for edge in payload['upper_witness']),
            payload.get('calibration_id'),
            None if k is None else Fraction(k[0], k[1]),
        )
        return SignedReview(report, ReviewReceipt(receipt['success_id'], receipt['report_id'],
                                                  tuple(receipt['material_ids'])))
