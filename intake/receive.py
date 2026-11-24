from intake.checks import check_packet


def receive_packet(receipts, raw):
    return receipts.record(check_packet(raw))
