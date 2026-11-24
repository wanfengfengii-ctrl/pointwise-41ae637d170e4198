from recording.evidence import SourceLocator
from recording.normalize import Endpoint
from recording.revisions import RevisionStore
from registry.batches import register_batch
from registry.history import BatchRegistry
from tests import support


class RecordingTests(support.ArchiveCase):
    def test_frozen_revision(self):
        original = support.sample('east.json')
        original['unit'] = 'ms'
        original['rows'][0]['reading'] = -2
        original['constraints'][0]['lower'] = support.endpoint(-3, False)
        old = self.freeze('east', original)
        replacement = support.sample('east.json')
        replacement['rows'][0]['position'] = 'redo:1'
        replacement['rows'][0]['reading'] = 7
        new = self.freeze('east', replacement)
        self.assertNotEqual(old.revision_id, new.revision_id)
        store = RevisionStore(self.revisions['east'].path)
        with store.transaction() as db:
            db.execute('CREATE TABLE operator_notes(note TEXT)')
            db.execute('INSERT INTO operator_notes VALUES (?)', ('keep calibration note',))
        store.initialize()
        self.assertEqual(store.get(old.revision_id), old)
        self.assertEqual(store.get(new.revision_id), new)
        self.assertEqual([row.row_id for row in old.rows], ['e1', 'x-read', 'e2', 'e3'])
        self.assertEqual(old.rows[0].reading, -2000000)
        self.assertEqual(old.constraints[0].lower, Endpoint(-3000000, False))
        self.assertEqual(old.constraints[0].upper, Endpoint(1000000, True))
        self.assertIsNone(old.constraints[1].lower)
        self.assertEqual(old.locations[0], SourceLocator(support.BATCH, 'east', old.revision_id,
                                                       'e1', 1, 'trace-A:1'))
        self.assertEqual(new.locations[0].position, 'redo:1')
        with store.connection() as db:
            self.assertEqual(db.execute('SELECT note FROM operator_notes').fetchall(),
                             [('keep calibration note',)])

    def test_revision_binding(self):
        east = self.freeze('east')
        west = self.freeze('west')
        self.assertEqual({item.marker: item.anchor for item in east.bindings},
                         {'cam-start': 'X', 'cam-peak': 'Y'})
        self.assertEqual({item.marker: item.anchor for item in west.bindings},
                         {'pulse': 'X', 'crest': 'Y'})
        self.assertEqual(east.batch, west.batch)

    def test_registry_history(self):
        document = support.sample('batch.json')
        for field in ('anchors', 'stations', 'bindings'):
            document[field].reverse()
        reopened = BatchRegistry(self.registry.path)
        reopened.initialize()
        self.assertEqual(register_batch(reopened, document), self.batch)
        self.assertEqual(reopened.get_snapshot(support.BATCH), self.batch)
        self.assertEqual(self.row_count(reopened, 'batches'), 1)
        with self.assertRaises(KeyError):
            reopened.get_snapshot('unknown-batch')

    def test_registry_conflict(self):
        document = support.sample('batch.json')
        document['anchors'][0]['meaning'] = 'different trigger'
        with self.assertRaises(ValueError):
            register_batch(self.registry, document)
        for binding in ({'station': 'east', 'marker': 'cam-start', 'anchor': 'Y'},
                        {'station': 'north', 'marker': 'start', 'anchor': 'X'},
                        {'station': 'west', 'marker': 'other', 'anchor': 'unknown'}):
            with self.subTest(binding=binding):
                document = support.sample('batch.json')
                document['bindings'].append(binding)
                with self.assertRaises(ValueError):
                    register_batch(self.registry, document)
        self.assertEqual(self.registry.get_snapshot(support.BATCH), self.batch)
        self.assertEqual(self.row_count(self.registry, 'batches'), 1)

    def test_missing_evidence(self):
        document = support.sample('east.json')
        document['rows'].pop(0)
        store = self.revisions['east']
        with self.assertRaisesRegex(ValueError, 'missing evidence'):
            self.freeze('east', document)
        self.assertEqual(self.row_count(store, 'revisions'), 0)
        old = self.freeze('east')
        with self.assertRaisesRegex(ValueError, 'missing evidence'):
            self.freeze('east', document)
        self.assertEqual(self.row_count(store, 'revisions'), 1)
        self.assertEqual(store.get(old.revision_id), old)

    def test_bad_units_and_markers(self):
        errors = [('unit', 'minutes'), ('reading', True), ('closed', 1),
                  ('from', 'absent marker'), ('evidence', None), ('missing-upper', None)]
        for kind, value in errors:
            with self.subTest(kind=kind):
                document = support.sample('east.json')
                relation = document['constraints'][0]
                if kind == 'unit':
                    document[kind] = value
                elif kind == 'reading':
                    document['rows'][0][kind] = value
                elif kind == 'closed':
                    relation['upper'][kind] = value
                elif kind == 'missing-upper':
                    del relation['upper']
                else:
                    relation[kind] = value
                with self.assertRaises(ValueError):
                    self.freeze('east', document)
        self.assertEqual(self.row_count(self.revisions['east'], 'revisions'), 0)
