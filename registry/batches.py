from archive import fields, label
from registry.anchors import collect_shared_anchors
from registry.bindings import collect_stations, validate_bindings
from registry.history import RegisteredBatch


def register_batch(registry, document):
    fields(document, 'batch stations anchors bindings', 'batch declaration')
    batch = label(document['batch'], 'batch')
    stations = collect_stations(document['stations'])
    anchors = collect_shared_anchors(document['anchors'])
    bindings = validate_bindings(stations, anchors, document['bindings'])
    return registry.save_snapshot(RegisteredBatch(batch, stations, anchors, bindings))
