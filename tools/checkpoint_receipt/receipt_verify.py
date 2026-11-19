"""Integrity checks for trusted receipts in a quiescent, exclusively owned workspace.

A digest is not authentication. This check does not guard against concurrent
replacement; the caller must hold its writer lock until the consumer finishes.
"""
import hashlib
import json
import re
from pathlib import Path


def _unique(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate receipt key")
        out[key] = value
    return out


def _inside(root, value, *, basename=False):
    if type(value) is not str or not value or '\\' in value:
        raise ValueError("invalid path")
    parts = value.split('/')
    if value.startswith('/'):
        if basename:
            raise ValueError("expected basename")
        try:
            value = str(Path(value).relative_to(root))
        except ValueError:
            raise ValueError("outside workspace") from None
        parts = value.split('/')
    if any(part in ('', '.', '..') for part in parts) or (basename and len(parts) != 1):
        raise ValueError("invalid path components")
    p = root
    for part in parts:
        p = p / part
        if p.is_symlink():
            raise ValueError("symlink not permitted")
    return p


def _digest(path, expected):
    if type(expected) is not str or not re.fullmatch('[0-9a-f]{64}', expected):
        raise ValueError("invalid digest")
    if not path.is_file():
        raise ValueError("missing regular file")
    with path.open('rb') as f:
        actual = hashlib.file_digest(f, 'sha256').hexdigest()
    if actual != expected:
        raise ValueError(f"digest mismatch: {path.name}")


def verify(receipt, workspace, *, required_files, required_identity=()):
    root = Path(workspace).resolve(strict=True)
    path = _inside(root, str(receipt))
    if not root.is_dir() or not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ValueError("invalid receipt file")
    doc = json.loads(path.read_text(), object_pairs_hook=_unique)
    if type(doc) is not dict or set(doc) != {'directory','next_cycle','files','identity'}:
        raise ValueError("invalid receipt schema")
    if type(doc['next_cycle']) is not int or doc['next_cycle'] < 0:
        raise ValueError("invalid cycle")
    cp = _inside(root, doc['directory'])
    if not cp.is_dir():
        raise ValueError("missing checkpoint")
    files, identity = doc['files'], doc['identity']
    if type(files) is not dict or type(identity) is not dict or not files or not identity:
        raise ValueError("missing inventory")
    if not set(required_files) or not set(required_files) <= files.keys():
        raise ValueError("required checkpoint files absent")
    known_ids = [_inside(root, name) for name in identity]
    if len(set(known_ids)) != len(known_ids):
        raise ValueError("duplicate normalized identity paths")
    if not {_inside(root, name) for name in required_identity} <= set(known_ids):
        raise ValueError("required execution identity absent")
    for name, expected in files.items():
        _digest(_inside(cp, name, basename=True), expected)
    for path, expected in zip(known_ids, identity.values()):
        _digest(path, expected)
    return doc
