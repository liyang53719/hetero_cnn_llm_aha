"""Bounded opaque event serialization over byte-pinned LEC1. No arithmetic."""
import hashlib
import importlib
import inspect
import json
import struct
from pathlib import Path
import sys
import types
from .source_guard import require, same_code, code_child

CODEC_PINS = {
    'format.py': '936f01ff9c7152c4752305c60c1442489f4fa8d71c08d7a38458d9f9690c76c5',
    'writer.py': '488eb96d5008f079b5717a9a029c39b4530e118788b7da747dd2ae109fcd9b5a',
    'decoder.py': '6f93cf8b6929a840f725c539a53a96f95e369b47920b4e36b4eaf0ac5d570f89',
}

EXP_ENVELOPE_SCHEMA = 'fixed93-attention-exp-envelope-v1'
EXP_METADATA_SCHEMA = 'fixed93-attention-exp-nodes-v1'
EXP_LAYOUT = 'u32le[operation(0=mul,1=add),a,b,result]'
EXP_METADATA_MAX = 332
EVENT_METADATA_MAX = 128


def _exp_canonical(metadata):
    """Validate the original flat metadata and recover its exact canonical bytes."""
    require(type(metadata) is dict and set(metadata) == {
        'schema', 'sequence', 'kind', 'tick', 'head', 'token', 'key', 'node_count',
        'returned_word', 'layout', 'unobserved_trailing_nodes'}, 'exp metadata keys')
    require(metadata['schema'] == EXP_METADATA_SCHEMA and metadata['kind'] == 'exp_nodes' and
            metadata['layout'] == EXP_LAYOUT, 'exp metadata schema/layout')
    require(all(type(metadata[k]) is int and 0 <= metadata[k] < 1 << 64
                for k in ('sequence', 'tick', 'head', 'token', 'key')), 'exp coordinate width')
    require(type(metadata['node_count']) is int and metadata['node_count'] in (1, 17) and
            type(metadata['unobserved_trailing_nodes']) is int and
            metadata['unobserved_trailing_nodes'] == 17 - metadata['node_count'], 'exp node extent')
    require(type(metadata['returned_word']) is int and 0 <= metadata['returned_word'] < 1 << 32,
            'exp returned word width')
    canonical = json.dumps(metadata, sort_keys=True, separators=(',', ':'),
                           ensure_ascii=True, allow_nan=False).encode('ascii')
    require(len(canonical) <= EXP_METADATA_MAX, 'exp canonical metadata bound')
    return canonical


def encode_exp_envelope(metadata, raw):
    """u32le header length, complete old canonical metadata, unchanged typed nodes."""
    canonical = _exp_canonical(metadata)
    require(type(raw) is bytes and len(raw) == metadata['node_count'] * 16, 'exp raw node extent')
    require(all(row[0] in (0, 1) for row in struct.iter_unpack('<4I', raw)), 'unknown exp operation')
    return len(canonical).to_bytes(4, 'little') + canonical + raw


def decode_exp_envelope(envelope, outer_metadata):
    """Bounded representation decoder. Returns old metadata and exact old raw bytes.

    The LEC1 decoder remains responsible for the outer record chain/seal. This
    decoder accepts one exp EVENT payload, not a stream or a partial prefix.
    """
    require(type(outer_metadata) is dict and set(outer_metadata) == {'schema', 'sequence', 'kind'},
            'exp envelope outer metadata keys')
    require(outer_metadata['schema'] == EXP_ENVELOPE_SCHEMA and
            outer_metadata['kind'] == 'exp_nodes' and type(outer_metadata['sequence']) is int and
            0 <= outer_metadata['sequence'] < 1 << 64, 'exp envelope outer metadata schema')
    require(type(envelope) is bytes and 4 <= len(envelope) <= 4 + EXP_METADATA_MAX + 272,
            'exp envelope byte bound')
    length = int.from_bytes(envelope[:4], 'little')
    require(1 <= length <= EXP_METADATA_MAX and 4 + length <= len(envelope), 'exp header extent')
    canonical = envelope[4:4 + length]
    try:
        metadata = json.loads(canonical)
        require(_exp_canonical(metadata) == canonical, 'noncanonical or duplicate exp metadata')
    except (TypeError, ValueError, UnicodeError, RecursionError) as error:
        raise ValueError('invalid exp envelope metadata') from error
    require(metadata['sequence'] == outer_metadata['sequence'], 'exp outer/inner sequence mismatch')
    raw = envelope[4 + length:]
    require(encode_exp_envelope(metadata, raw) == envelope, 'exp envelope mismatch')
    return metadata, raw


def event_bytes(values):
    """Canonical flat JSON; tuples become lists, bytes use explicit hex suffix.

    All integers are exact JSON integers, never float coercions. No more than
    64 keys/256 words per tuple/1024 bytes per payload. Decoder json.loads
    recovers each integer and bytes.fromhex recovers each *_bytes_hex value.
    """
    require(type(values) is dict and len(values) <= 64, 'event key bound')
    flat = {}
    for key, value in values.items():
        require(type(key) is str and 0 < len(key) <= 64 and not key.endswith('_bytes_hex'), 'event key schema')
        if type(value) is bytes:
            require(len(value) <= 1024, 'event byte payload bound')
            flat[key + '_bytes_hex'] = value.hex()
        elif type(value) is tuple:
            require(len(value) <= 256 and all(type(x) is int and 0 <= x < 1 << 32 for x in value), 'event tuple word bound')
            flat[key] = list(value)
        elif value is None or type(value) is bool:
            flat[key] = value
        elif type(value) is int:
            require(-(1 << 63) <= value < 1 << 64, 'event integer width')
            flat[key] = value
        elif type(value) is str:
            require(len(value) <= 512, 'event string bound')
            flat[key] = value
        else:
            raise ValueError('unsupported event value: ' + key)
    raw = json.dumps(flat, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')
    require(len(raw) <= 16384, 'event encoded size bound')
    return raw


def load_codec(root):
    """Load only this qualified opaque codec, never model/native modules.

    The upstream codec deliberately uses top-level 'format'/'writer'. Refuse
    collisions, do not replace module globals or execute copied/edited code.
    """
    root = Path(root).resolve()
    for filename, digest in CODEC_PINS.items():
        require(hashlib.sha256((root / filename).read_bytes()).hexdigest() == digest, 'codec source drift: ' + filename)
    for name in ('format', 'writer'):
        loaded = sys.modules.get(name)
        require(loaded is None or Path(loaded.__file__).resolve() == root / (name + '.py'), 'codec top-level import collision')
    sys.path.insert(0, str(root))
    try:
        fmt, writer = importlib.import_module('format'), importlib.import_module('writer')
    finally:
        require(sys.path[0] == str(root), 'codec import path changed')
        del sys.path[0]
    # Inspect original function code and globals, including decorated Writer
    # implementations through __wrapped__. No constructor is called here.
    import ast
    for name, module in (('format', fmt), ('writer', writer)):
        path = root / (name + '.py')
        require(Path(module.__file__).resolve() == path, 'loaded codec path drift')
        text = path.read_text()
        compiled, tree = compile(text, str(path), 'exec', dont_inherit=True, optimize=0), ast.parse(text)
        for node in tree.body:
            targets = []
            if isinstance(node, ast.FunctionDef):
                targets.append((getattr(module, node.name), node, code_child(compiled, node.name)))
            elif isinstance(node, ast.ClassDef):
                class_code = code_child(compiled, node.name)
                cls = getattr(module, node.name)
                for method in node.body:
                    if isinstance(method, ast.FunctionDef):
                        targets.append((vars(cls).get(method.name), method, code_child(class_code, method.name)))
            for actual, node, expected in targets:
                original = inspect.unwrap(actual)
                if actual is not original:
                    require(name == 'writer' and same_code(actual.__code__, code_child(code_child(compiled, 'operation'), 'call')) and
                            len(actual.__closure__ or ()) == 1 and actual.__closure__[0].cell_contents is original,
                            'loaded codec decorator wrapper drift: ' + node.name)
                require(isinstance(original, types.FunctionType) and original.__globals__ is module.__dict__ and
                        same_code(original.__code__, expected), 'loaded codec implementation drift: ' + node.name)
    require(writer.CodecError is fmt.CodecError and writer.Limits is fmt.Limits, 'codec format dependency drift')
    return fmt, writer


class EventStream:
    def __init__(self, destination, trace_limits):
        self.destination = Path(destination).resolve()
        self.destination.mkdir(parents=True, exist_ok=False)
        self.path = self.destination / 'attention-events.lec1'
        self.fmt, self.module = load_codec(trace_limits['codec_root'])
        limits = self.fmt.Limits(**trace_limits['codec_limits'])
        require(limits.max_chunk >= 16384, 'codec chunk cannot hold bounded event schema')
        self.sink = self.path.open('xb')
        self.writer = self.module.Writer(self.sink, limits, byte_order='little')
        self.count, self.seal, self.failed = 0, None, False
        self.digest = hashlib.sha256()

    def emit(self, kind, tick, values):
        require(not self.failed and self.seal is None, 'event stream unavailable')
        raw = event_bytes(dict(sequence=self.count, kind=kind, tick=tick, **values))
        try:
            metadata = {'schema': 'fixed93-attention-event-v2', 'sequence': self.count, 'kind': kind}
            self.fmt.metadata_bytes(metadata, EVENT_METADATA_MAX)
            self.writer.event(raw, metadata)
        except BaseException:
            self.failed = True
            raise
        self.digest.update(len(raw).to_bytes(4, 'little'))
        self.digest.update(raw)
        self.count += 1

    def emit_exp_nodes(self, tick, head, token, key, nodes, returned_word):
        require(not self.failed and self.seal is None, 'event stream unavailable')
        require(type(nodes) is tuple and len(nodes) in (1, 17), 'exp node count outside frozen graph')
        require(all(type(row) is tuple and len(row) == 4 and all(type(v) is int and 0 <= v < 1 << 32 for v in row)
                    for row in nodes), 'typed exp actual word schema')
        raw = b''.join(struct.pack('<4I', *row) for row in nodes)
        metadata = dict(schema='fixed93-attention-exp-nodes-v1', sequence=self.count, kind='exp_nodes',
                        tick=tick, head=head, token=token, key=key, node_count=len(nodes), returned_word=returned_word,
                        layout='u32le[operation(0=mul,1=add),a,b,result]', unobserved_trailing_nodes=17-len(nodes))
        try:
            envelope = encode_exp_envelope(metadata, raw)
            outer = dict(schema=EXP_ENVELOPE_SCHEMA, sequence=self.count, kind='exp_nodes')
            self.fmt.metadata_bytes(outer, EVENT_METADATA_MAX)
            self.writer.event(envelope, outer)
        except BaseException:
            self.failed = True
            raise
        # This is the existing logical-observation digest, not the changed
        # LEC1 representation digest. A decoder recovers these same two bytes.
        canonical = _exp_canonical(metadata)
        self.digest.update(len(canonical).to_bytes(4, 'little')); self.digest.update(canonical)
        self.digest.update(len(raw).to_bytes(4, 'little')); self.digest.update(raw)
        self.count += 1

    def close(self):
        try:
            if not self.failed:
                self.seal = self.writer.finish()
        finally:
            self.sink.close()
        return self.seal
