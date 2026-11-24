from dataclasses import dataclass

from archive import array, fields, label


@dataclass(frozen=True)
class SharedAnchor:
    name: str
    meaning: str


def collect_shared_anchors(declarations):
    anchors = {}
    meanings = set()
    for item in array(declarations, 'anchors'):
        fields(item, 'name meaning', 'anchor')
        name = label(item['name'], 'anchor name')
        meaning = label(item['meaning'], 'anchor meaning')
        if name in anchors or meaning in meanings:
            raise ValueError('anchor names and meanings must be unique within the batch')
        anchors[name] = SharedAnchor(name, meaning)
        meanings.add(meaning)
    if not anchors:
        raise ValueError('the batch must declare a shared anchor')
    return tuple(anchors[name] for name in sorted(anchors))
