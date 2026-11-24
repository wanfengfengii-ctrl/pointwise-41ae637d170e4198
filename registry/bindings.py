from dataclasses import dataclass

from archive import array, fields, label, unique_labels


@dataclass(frozen=True)
class MarkerBinding:
    station: str
    marker: str
    anchor: str


def collect_stations(declarations):
    stations = unique_labels(declarations, 'stations')
    if len(stations) != 2:
        raise ValueError('the batch requires two distinct stations')
    return tuple(sorted(stations))


def validate_bindings(stations, anchors, declarations):
    names = {anchor.name for anchor in anchors}
    bindings = {}
    for item in array(declarations, 'bindings'):
        fields(item, 'station marker anchor', 'binding')
        station = label(item['station'], 'binding station')
        marker = label(item['marker'], 'binding marker')
        anchor = label(item['anchor'], 'binding anchor')
        if station not in stations or anchor not in names:
            raise ValueError('binding must refer to a member and a declared anchor')
        key = (station, marker)
        binding = MarkerBinding(station, marker, anchor)
        if key in bindings and bindings[key] != binding:
            raise ValueError(f'conflicting binding for {station}/{marker}')
        bindings[key] = binding
    return tuple(bindings[key] for key in sorted(bindings))


def resolve_revision_bindings(batch, station, markers):
    if station not in batch.stations:
        raise ValueError(f'{station} is not a member of {batch.batch}')
    return tuple(binding for binding in batch.bindings
                 if binding.station == station and binding.marker in markers)
