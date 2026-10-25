"""Public encoder fixtures for FFN4 and the original Qwen2 21-op schedule.

FFN4 remains a separate subprogram. The opt-in full-block fixture reuses the
retained public packers and builds metadata only, never numeric payloads.
"""
from dataclasses import dataclass, field
import hashlib
import importlib.util
from math import prod
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import MappingProxyType

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))
from heteronpu.command import Command128, Engine, Opcode
from heteronpu.descriptor_chain import DescriptorRecord, MatrixAux, SfuProgram, TensorDType
from heteronpu.gemmini_descriptor_v2 import tensor_base_record, shape4_record, stride3_record, matrix_op_record

try:
    from .model import LaunchConfig, MetadataMemory, NULL, LIMIT, Region, Table, align64
except ImportError:
    from model import LaunchConfig, MetadataMemory, NULL, LIMIT, Region, Table, align64


QWEN2_21_SOURCE_COMMIT = '8212a32f43338163baee4126e522dcacede0fa23'
QWEN2_21_SOURCE_PINS = (
    ('chisel/continuous_prefill/scripts/pack_owner_block_fixture.py',
     '3efc7bb21b66bd16f757b8aac99c779ad3efe9289115e6ea7d5628a4ff6c2154'),
    ('chisel/continuous_prefill/scripts/pack_owner_bf16_weights.py',
     '17347fccdf73f54692b4e1c8047a26154f55348f06dca87c5c2db7def515c692'),
)
QWEN2_21_WORKSPACE_BYTES = 786432


@dataclass(frozen=True)
class PhysicalAllocation:
    """A true reservation, including the original FP32-sized weight guard half."""
    address: int
    shape: tuple
    dtype: int
    reserved_bytes: int
    readonly: bool
    virtual: bool = False

    @property
    def storage_bytes(self):
        return align64(prod(self.shape) * (2 if self.dtype == 5 else 4))

    @property
    def limit(self):
        return self.address + self.reserved_bytes


@dataclass(frozen=True)
class AllocationView:
    """A typed subview of one allocation, not an independent reservation."""
    allocation: str
    offset_bytes: int
    shape: tuple
    dtype: int

    @property
    def storage_bytes(self):
        return align64(prod(self.shape) * (2 if self.dtype == 5 else 4))


@dataclass
class Fixture:
    config: LaunchConfig
    memory: MetadataMemory
    commands: tuple
    records: tuple
    roots: tuple
    specs: dict
    scope: str = 'FFN4_COMMAND_SUBPROGRAM_ONLY'
    allocations: dict = field(default_factory=dict)
    views: dict = field(default_factory=dict)
    manifest: dict = field(default_factory=dict)
    provenance: object = field(default_factory=dict)

    def physical_spans(self):
        if self.allocations:
            spans = [(name, a.address, a.limit) for name, a in self.allocations.items()]
        else:
            spans = [(name, address, address + align64(prod(shape) * (2 if dtype == 5 else 4)))
                     for name, (address, shape, dtype) in self.specs.items()]
        spans += [('command_table', self.config.command.base, self.config.command.limit),
                  ('descriptor_table', self.config.descriptor.base, self.config.descriptor.limit),
                  ('workspace', self.config.regions[3].base, self.config.regions[3].limit)]
        return spans

    def validate_spans(self):
        if self.allocations:
            if set(self.specs) != set(self.allocations) | set(self.views):
                raise ValueError('fixture allocation/view coverage')
            if set(self.allocations) & set(self.views):
                raise ValueError('fixture view is not an independent allocation')
            for name, a in self.allocations.items():
                if (not 1 <= len(a.shape) <= 4 or any(type(n) is not int or n <= 0 for n in a.shape)
                        or a.dtype not in (5, 7) or type(a.address) is not int
                        or type(a.reserved_bytes) is not int or a.address < 0 or a.address % 64
                        or a.reserved_bytes % 64 or not 0 < a.storage_bytes <= a.reserved_bytes
                        or a.limit > LIMIT):
                    raise ValueError('physical fixture allocation extent')
                if self.specs[name] != (a.address, a.shape, a.dtype):
                    raise ValueError('fixture allocation/spec mismatch')
                if not any(r.base <= a.address < a.limit <= r.limit and r.read
                           and r.write == (not a.readonly) for r in self.config.ordinary_regions):
                    raise ValueError('physical fixture allocation permission')
            for name, view in self.views.items():
                a = self.allocations.get(view.allocation)
                if (a is None or type(view.offset_bytes) is not int or view.offset_bytes < 0
                        or view.offset_bytes % 64 or not 1 <= len(view.shape) <= 4
                        or any(type(n) is not int or n <= 0 for n in view.shape)
                        or view.dtype != a.dtype or view.offset_bytes + view.storage_bytes > a.storage_bytes):
                    raise ValueError('fixture view outside its allocation')
                if self.specs[name] != (a.address + view.offset_bytes, view.shape, view.dtype):
                    raise ValueError('fixture view/spec mismatch')
        spans = self.physical_spans()
        for i, (name, a, b) in enumerate(spans):
            for other, c, d in spans[i + 1:]:
                if a < d and c < b:
                    raise ValueError(f'physical fixture allocation overlap: {name}, {other}')
        return spans


def make_ffn4_fixture(rows=16, epoch=7, relocate=0):
    if rows not in (16, 128):
        raise ValueError('resident FFN profile requires M16 or M128')
    if type(relocate) is not int or relocate < 0 or relocate % 64:
        raise ValueError('physical fixture relocation must be nonnegative and 64-byte aligned')
    h, f = 1536, 8960
    specs = {
        'n1': (0x1000000, (rows, h), 7),
        'gate_weight': (0x2000000, (h, f), 5),
        'up_weight': (0x4000000, (h, f), 5),
        'down_weight': (0x6000000, (f, h), 5),
        'gate': (0x8000000, (rows, f), 7),
        'up': (0x9000000, (rows, f), 7),
        'act': (0xa000000, (rows, f), 7),
        'down': (0xb000000, (rows, h), 7),
    }
    specs = {name: (address + relocate, shape, dtype) for name, (address, shape, dtype) in specs.items()}
    records, commands, roots = [], [], []

    def chain(name, extra=()):
        address, shape, dtype = specs[name]
        dims = shape + (1,) * (4 - len(shape))
        root = len(records)
        records.extend((tensor_base_record(address, dtype=dtype, rank=len(shape), next_index=root + 1),
            shape4_record(dims, next_index=root + 2),
            stride3_record((dims[1] * dims[2] * dims[3], dims[2] * dims[3], dims[3]),
                           next_index=root + 3 if extra else NULL)))
        for i, r in enumerate(extra):
            records.append(DescriptorRecord(r.record_type, r.subtype, r.flags,
                root + 4 + i if i + 1 < len(extra) else NULL, r.payload))
        return root

    def emit(op, a, b, d, extra):
        r = chain(a, extra), chain(b), chain(d)
        pc = len(commands)
        commands.append(Command128(op, Engine.MATRIX if op == Opcode.MATRIX_GEMM else Engine.SFU_CGRA,
            event_wait=pc, event_signal=pc + 1, src0=r[0], src1=r[1], dst=r[2]))
        roots.append(r)

    def matrix(a, b, d, m, n, k):
        emit(Opcode.MATRIX_GEMM, a, b, d,
             (matrix_op_record(m=m, n=n, k=k, dataflow=0), MatrixAux(full_c=True).to_record()))

    matrix('n1', 'gate_weight', 'gate', rows, f, h)
    matrix('n1', 'up_weight', 'up', rows, f, h)
    emit(Opcode.SFU_ACTIVATION, 'gate', 'up', 'act',
         (SfuProgram(0x35, 2, input_dtype=TensorDType.FP32, output_dtype=TensorDType.FP32).to_record(),))
    matrix('act', 'down_weight', 'down', rows, h, f)
    cb = b''.join(c.to_bytes() for c in commands)
    db = b''.join(r.pack().to_bytes(16, 'little') for r in records)
    cb_base, db_base = 0xc000000 + relocate, 0xc001000 + relocate
    c, d = Table(cb_base, cb_base + align64(len(cb)), len(commands)), Table(db_base, db_base + align64(len(db)), len(records))
    regions = (Region(0x1000000 + relocate, 0x8000000 + relocate, True, False),
               Region(0x8000000 + relocate, 0xc000000 + relocate, True, True),
               Region(0xc000000 + relocate, 0xc010000 + relocate, True, False),
               Region(0x10000000 + relocate, 0x100c0000 + relocate, True, True))
    cfg = LaunchConfig(c, d, regions, epoch)
    cfg.validate()
    memory = MetadataMemory(((c.base, cb.ljust(align64(len(cb)), b'\0')),
                             (d.base, db.ljust(align64(len(db)), b'\0'))))
    fixture = Fixture(cfg, memory, tuple(commands), tuple(records), tuple(roots), specs)
    fixture.validate_spans()
    return fixture


def _qwen2_21_packers():
    """Verify retained source before importing the two existing metadata packers."""
    modules = []
    for path, expected in QWEN2_21_SOURCE_PINS:
        source = ROOT / path
        if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
            raise ValueError(f'Qwen2 public fixture source pin drift: {path}')
        spec = importlib.util.spec_from_file_location('_qwen2_21_' + source.stem, source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules.append(module)
    return modules[0].pack, modules[1].convert


def _metadata_temporary_directory(metadata_parent, metadata_root):
    """Legacy cleanup by default; explicitly bounded metadata is retained.

    The source-bound caller supplies its fresh output root. These path arguments
    are not execution authority, and do not replace the worker's output gate.
    No shutil/tempfile globals or relative-open audit rules are changed.
    """
    if metadata_parent is None and metadata_root is None:
        return TemporaryDirectory(prefix='qwen2_21_metadata_')
    if not isinstance(metadata_parent, (str, Path)) or not isinstance(metadata_root, (str, Path)):
        raise ValueError('persistent metadata requires both explicit path arguments')
    parent, root = Path(metadata_parent), Path(metadata_root)
    if not root.is_absolute() or not parent.is_absolute():
        raise ValueError('persistent metadata paths must be absolute')
    if not root.is_dir() or root.is_symlink() or root.resolve(strict=True) != root:
        raise ValueError('persistent metadata root must be an existing canonical directory')
    if parent != root / 'metadata' or parent.is_symlink() or parent.exists():
        raise ValueError('persistent metadata parent must be the fresh exact output child')
    if parent.resolve(strict=False) != parent:
        raise ValueError('persistent metadata parent must be canonical')
    parent.mkdir(mode=0o700)
    if parent.resolve(strict=True) != parent or parent.is_symlink():
        raise ValueError('persistent metadata parent changed')
    # Python 3.12 __exit__ and the weakref finalizer both skip rmtree when
    # delete=False. Retain the eight small metadata files even on failure.
    return TemporaryDirectory(prefix='qwen2_21_metadata_', dir=str(parent), delete=False)


def make_qwen2_21_fixture(rows=16, epoch=7, relocate=0, max_tokens=1024, *, metadata_parent=None, metadata_root=None):
    """Reuse the unchanged public21 command/descriptor packing, metadata only.

    No weight bytes, initial inputs or writable intermediates are materialized.
    Dense B storage alone changes FP32 dtype 7 to native BF16 dtype 5 through
    the retained converter; original addresses/reservations/shape/strides stay.
    Scores/probabilities retain virtual reservations for fused PCs 10--12.
    This fixture is neither official model data nor full-block numeric proof.
    """
    if type(rows) is not int or rows not in (16, 128):
        raise ValueError('resident Qwen2 profile requires M16 or M128')
    if type(epoch) is not int or not 0 <= epoch < 1 << 16:
        raise ValueError('physical fixture epoch must be an unsigned 16-bit integer')
    if type(relocate) is not int or relocate < 0 or relocate % 64:
        raise ValueError('physical fixture relocation must be nonnegative and 64-byte aligned')
    if type(max_tokens) is not int or max_tokens != 1024:
        raise ValueError('retained Qwen2 public fixture requires MAX_TOKENS=1024')
    if relocate >= LIMIT - 0x100000000:
        raise ValueError('physical fixture relocation exceeds the 56-bit address space')
    pack, convert = _qwen2_21_packers()
    shape = dict(H=1536, F=8960, HEADS=12, KVHEADS=2, HD=128, MAX_TOKENS=max_tokens)
    # Both helpers write only public metadata. Legacy defaults remove temporary
    # directories; explicit metadata_parent retains them. convert() never calls
    # its separate pack_words() helper.
    with _metadata_temporary_directory(metadata_parent, metadata_root) as temporary:
        source, output = Path(temporary) / 'fp32', Path(temporary) / 'bf16'
        original = pack(shape, rows, source, relocate)
        if original['limit'] + QWEN2_21_WORKSPACE_BYTES > LIMIT:
            raise ValueError('physical fixture arena/workspace exceeds the 56-bit address space')
        manifest = convert(source, output)
        cb = (output / 'host_commands.bin').read_bytes()
        db = (output / 'host_descriptors.bin').read_bytes()
    c = Table(manifest['commandBase'], manifest['commandLimit'], manifest['commands'])
    d = Table(manifest['descriptorBase'], manifest['descriptorLimit'], manifest['descriptors'])
    regions = (
        Region(manifest['metadataLimit'], manifest['scratchBase'], True, False),
        Region(manifest['scratchBase'], manifest['limit'], True, True),
        Region(manifest['base'], manifest['metadataLimit'], True, False),
        Region(manifest['limit'], manifest['limit'] + QWEN2_21_WORKSPACE_BYTES, True, True),
    )
    cfg = LaunchConfig(c, d, regions, epoch)
    cfg.validate()
    commands = tuple(Command128.from_bytes(cb[i * 16:(i + 1) * 16]) for i in range(c.count))
    records = tuple(DescriptorRecord.unpack(int.from_bytes(db[i * 16:(i + 1) * 16], 'little'))
                    for i in range(d.count))
    roots = tuple((cmd.src0, cmd.src1, cmd.dst) for cmd in commands)
    specs = {name: (t['address'], tuple(t['dims']), t.get('storage_dtype', 7))
             for name, t in manifest['tensors'].items()}
    allocations = {
        name: PhysicalAllocation(*specs[name], align64(t['words'] * 4), t['readonly'], t['virtual'])
        for name in manifest['allocations'] for t in (manifest['tensors'][name],)
    }
    kv = allocations['kv']
    views = {name: AllocationView('kv', specs[name][0] - kv.address, specs[name][1], specs[name][2])
             for name in ('cache_k', 'cache_v')}
    provenance = MappingProxyType(dict(source_commit=QWEN2_21_SOURCE_COMMIT,
        source_sha256=QWEN2_21_SOURCE_PINS, max_tokens=max_tokens,
        original_descriptor_sha256=manifest['weight_contract']['original_descriptor_sha256'],
        command_sha256=manifest['table_sha256']['host_commands.bin'],
        descriptor_sha256=manifest['table_sha256']['host_descriptors.bin'],
        tensor_payloads_materialized=False, official_weights=False, full_block_numeric_proof=False))
    fixture = Fixture(cfg, MetadataMemory(((c.base, cb), (d.base, db))), commands, records,
                      roots, specs, 'QWEN2_21_METADATA_ONLY', allocations, views, manifest, provenance)
    fixture.validate_spans()
    return fixture


def make_dense_fixture(rows=16, k=256, n=32, epoch=7):
    """Small public ordinary Dense transaction for transport/arithmetic tests.

    A is readonly initial input here; it does not stand in for FFN act output.
    Geometry is explicitly synthetic and is never full-FFN acceptance evidence.
    """
    specs = {'a': (0x1000000, (rows, k), 7), 'weight': (0x2000000, (k, n), 5),
             'dst': (0xb000000, (rows, n), 7)}
    records, roots = [], []
    for name, extra in (('a', (matrix_op_record(m=rows, n=n, k=k, dataflow=0), MatrixAux(full_c=True).to_record())),
                        ('weight', ()), ('dst', ())):
        address, dims, dtype = specs[name]
        root = len(records)
        roots.append(root)
        records.extend((tensor_base_record(address, dtype=dtype, rank=2, next_index=root + 1),
                        shape4_record(dims + (1, 1), next_index=root + 2),
                        stride3_record((dims[1], 1, 1), next_index=root + 3 if extra else NULL)))
        for i, r in enumerate(extra):
            records.append(DescriptorRecord(r.record_type, 0, 0, root + 4 + i if i + 1 < len(extra) else NULL, r.payload))
    cmd = Command128(Opcode.MATRIX_GEMM, Engine.MATRIX, event_signal=1,
                     src0=roots[0], src1=roots[1], dst=roots[2])
    c, d = Table(0xc000000, 0xc000040, 1), Table(0xc001000, 0xc001000 + align64(len(records) * 16), len(records))
    base = make_ffn4_fixture(16, epoch)
    cfg = LaunchConfig(c, d, base.config.regions, epoch)
    db = b''.join(r.pack().to_bytes(16, 'little') for r in records)
    mem = MetadataMemory(((c.base, cmd.to_bytes().ljust(64, b'\0')), (d.base, db.ljust(d.limit - d.base, b'\0'))))
    fixture = Fixture(cfg, mem, (cmd,), tuple(records), (tuple(roots),), specs, 'SYNTHETIC_DENSE_ONLY')
    fixture.validate_spans()
    return fixture
