import json
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path


def canonical_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                      separators=(',', ':')).encode('utf-8')


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError(f'invalid JSON constant: {value}')


def decode_json(raw):
    return json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_object,
                      parse_constant=_invalid_constant)


def fields(value, names, context):
    if not isinstance(value, dict) or value.keys() != set(names.split()):
        raise ValueError(f'invalid fields for {context}')
    return value


def array(value, context):
    if not isinstance(value, list):
        raise ValueError(f'{context} must be an array')
    return value


def label(value, context):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{context} must be nonempty text')
    value.encode('utf-8')
    return value


def unique_labels(value, context):
    result = tuple(label(item, context) for item in array(value, context))
    if len(set(result)) != len(result):
        raise ValueError(f'duplicate entries for {context}')
    return result


def positive_id(value, context):
    if type(value) is not int or value <= 0:
        raise ValueError(f'{context} must be a positive integer')
    return value


def lookup_id(value, context):
    positive_id(value, context)
    if value > 2**63 - 1:
        raise KeyError(value)
    return value


class SqliteArchive:
    def __init__(self, path):
        self.path = Path(path)

    @contextmanager
    def connection(self):
        with closing(sqlite3.connect(self.path, isolation_level=None)) as db:
            db.execute('PRAGMA foreign_keys = ON')
            yield db

    @contextmanager
    def transaction(self):
        with self.connection() as db, db:
            db.execute('BEGIN IMMEDIATE')
            yield db

    def create_tables(self, *statements):
        with self.transaction() as db:
            for statement in statements:
                db.execute(statement)
