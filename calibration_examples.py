import argparse
import json
import sqlite3
from contextlib import contextmanager
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from archive import canonical_bytes
from intake.checks import PacketValidationError
from intake.receive import receive_packet
from intake.store import ReceiptConflictError, ReceiptStore
from issue.register import IssueRegister, issue_packet
from recording.intake import freeze_recording
from recording.revisions import RevisionStore
from registry.batches import register_batch
from registry.history import BatchRegistry
from review.align import Conflict, review_pair
from review.lookup import get_report
from review.reports import ReportStore, ReportWriteError, SignedReview


SAMPLES = Path(__file__).resolve().parent / "samples"
EW = {("east", "e1"), ("east", "e2")}
WEST = {("west", "w1")}
CASES = {
    "handoff": [(-1, "Y", None, EW | WEST),
                (1, "Y", ((1, False), (3, False)), (WEST, EW))],
    "crossing": [(Fraction(-1, 2), "Y", ((-10, False), (Fraction(3, 2), False)), (WEST, EW)),
                 (0, "Y", ((-10, False), (2, True)), (WEST, {("east", "e3")})),
                 (Fraction(1, 2), "Y", ((-10, False), (2, True)), (WEST, {("east", "e3")}))],
    "local": [(0, "X", None, {("east", "e4"), ("east", "e5")}),
              (1, "X", ((0, False), (0, False)), (set(), set()))],
}


def sample(name):
    return json.loads((SAMPLES / (name + ".json")).read_text(encoding="utf-8"))


def affine(a, b=0, closed=True):
    return dict(a=a, b=b, closed=closed)


def documents(case):
    east, west = sample("east"), sample("west")
    for document in (east, west):
        document["calibration"] = {"id": "clock-gain", "range": [[-1, 1], [1, 1]]}
    east["constraints"][0]["upper"] = affine(1, 1)
    east["constraints"][1]["upper"] = affine(1)
    west["constraints"][0]["lower"] = affine(2, -1) if case == "handoff" else affine(-10)
    if case == "crossing":
        east["constraints"].append({"from": "cam-start", "to": "cam-peak", "lower": None,
                                    "upper": affine(2, closed=False), "evidence": "e3"})
    if case == "local":
        east["rows"].extend([
            dict(id="e4", marker="room-only-left", reading=50, position="spare:1"),
            dict(id="e5", marker="room-only-right", reading=60, position="spare:2"),
        ])
        east["constraints"].extend([
            {"from": "room-only-left", "to": "room-only-right", "lower": None,
             "upper": affine(0), "evidence": "e4"},
            {"from": "room-only-right", "to": "room-only-left", "lower": None,
             "upper": affine(0, 1, False), "evidence": "e5"},
        ])
    return east, west


def snapshot(store):
    with store.connection() as db:
        return tuple(db.iterdump())


def reject(error, action, store):
    before = snapshot(store)
    try:
        action()
    except error:
        pass
    else:
        raise AssertionError(f"expected {error.__name__}")
    assert snapshot(store) == before


class RefusedCommit(ReportStore):
    @contextmanager
    def transaction(self):
        with super().transaction() as db:
            yield db
            raise sqlite3.OperationalError("calibration report commit refused")


def run(case, show=False):
    with TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "station-files"
        source.mkdir()
        registry = BatchRegistry(source / "batches.sqlite")
        registry.initialize()
        batch = register_batch(registry, sample("batch")).batch
        center = root / "desk.sqlite"
        receipts, reports = ReceiptStore(center), ReportStore(center)
        receipts.initialize()
        reports.initialize()
        ticket_sources = {}

        def handoff(station, doc):
            revisions = RevisionStore(source / f"{station}-revisions.sqlite")
            issues = IssueRegister(source / f"{station}-issues.sqlite")
            revisions.initialize()
            issues.initialize()
            frozen = freeze_recording(registry, revisions, batch, station, doc)
            packet = issue_packet(RevisionStore(revisions.path), issues, batch, station, frozen.revision_id)
            assert IssueRegister(issues.path).get_packet(packet.issue_id).raw == packet.raw
            envelope = json.loads(packet.raw)
            assert envelope["version"] == (2 if "calibration" in doc else 1)
            if "calibration" in doc:
                for row in doc["rows"]:
                    for field in ("marker", "position"):
                        assert json.dumps(row[field]).encode() not in packet.raw
            material = receive_packet(receipts, packet.raw)
            assert receipts.get(material.receipt_id).raw == packet.raw
            assert receive_packet(receipts, packet.raw).receipt_id == material.receipt_id
            for ticket in envelope["body"]["tickets"]:
                locator = issues.locate_origin(packet.issue_id, ticket)
                assert locator.revision_id == frozen.revision_id and locator.station == station
                ticket_sources[material.receipt_id, ticket] = (station, locator.row_id)
            return material

        east_doc, west_doc = documents(case)
        east = handoff("east", east_doc)
        west = handoff("west", west_doc)
        if case == "handoff":
            legacy = handoff("west", sample("west"))
            other = deepcopy(west_doc)
            other["calibration"]["id"] = "other-gain"
            wrong_id = handoff("west", other)
            other = deepcopy(west_doc)
            other["calibration"]["range"][0] = [-2, 1]
            wrong_range = handoff("west", other)
        source.rename(root / "closed-stations")
        assert not source.exists()
        receipts = ReceiptStore(center)

        def resolve(witness):
            return {ticket_sources[edge.origin.receipt_id, ticket]
                    for edge in witness for ticket in edge.tickets}

        def ask(k, y="Y", second=west.receipt_id, desk=reports):
            return review_pair(receipts, desk, east.receipt_id, second, "X", y, k=k)

        for k, y, expected, proofs in CASES[case]:
            before = snapshot(reports)
            result = ask(k, y)
            if expected is None:
                assert isinstance(result, Conflict) and resolve(result.witness) == proofs
                assert snapshot(reports) == before
                if show:
                    print(f"{case} k={k} X->{y} conflict: {sorted(resolve(result.witness))}")
                continue
            assert isinstance(result, SignedReview)
            report = result.report
            assert report.calibration_id == "clock-gain" and report.k == k
            assert type(report.k) in (int, Fraction)
            assert {origin.receipt_id for origin in report.origins} == {east.receipt_id, west.receipt_id}
            assert set(result.receipt.material_ids) == {east.receipt_id, west.receipt_id}
            limits = (report.interval.lower, report.interval.upper)
            assert all(type(bound.value) in (int, Fraction) for bound in limits)
            assert tuple((bound.value, bound.strict) for bound in limits) == expected
            assert (resolve(report.lower_witness), resolve(report.upper_witness)) == proofs
            historical = get_report(ReportStore(center), report.report_id)
            assert historical == result
            if show:
                lo, hi = historical.report.interval.lower, historical.report.interval.upper
                span = ("(" if lo.strict else "[") + f"{lo.value},{hi.value}" + (")" if hi.strict else "]")
                print(f"{case} k={k} X->{y} {span} ns, materials {historical.receipt.material_ids}, "
                      f"retrieved report {historical.report.report_id} / {historical.receipt.success_id}")

        if case == "handoff" and not show:
            for other in (legacy, wrong_id, wrong_range):
                reject(ValueError, lambda: ask(1, second=other.receipt_id), reports)
            reject(ValueError, lambda: ask(Fraction(3, 2)), reports)
            reject(ReportWriteError, lambda: ask(1, desk=RefusedCommit(center)), reports)
            assert isinstance(ask(1, desk=ReportStore(center)), SignedReview)
            damaged = json.loads(east.raw)
            damaged["body"]["calibration"]["range"].reverse()
            reject(PacketValidationError, lambda: receive_packet(receipts, canonical_bytes(damaged)), receipts)
            damaged.pop("sha256")
            damaged["sha256"] = sha256(canonical_bytes(damaged)).hexdigest()
            reject(PacketValidationError, lambda: receive_packet(receipts, canonical_bytes(damaged)), receipts)
            reject(ReceiptConflictError, lambda: receive_packet(receipts, b" " + east.raw), receipts)


def main():
    parser = argparse.ArgumentParser(description="Calibration handoff examples")
    parser.add_argument("action", choices=("inputs", "verify", "demo"))
    args = parser.parse_args()
    if args.action == "inputs":
        print(json.dumps({"batch": sample("batch"), "cases": {name: documents(name) for name in CASES}},
                         ensure_ascii=False, indent=2))
    elif args.action == "demo":
        run("handoff", show=True)
    else:
        for case in CASES:
            run(case)
        print("Calibration handoff, crossing and local conflict verified.")


if __name__ == "__main__":
    main()
