from dataclasses import dataclass

from recording.evidence import SourceLocator


@dataclass(frozen=True)
class OriginTicket:
    ticket: str
    source: SourceLocator


def issue_origin_tickets(qualified):
    return tuple(OriginTicket(f'p{number}', location)
                 for number, location in enumerate(qualified.revision.locations, start=1))
