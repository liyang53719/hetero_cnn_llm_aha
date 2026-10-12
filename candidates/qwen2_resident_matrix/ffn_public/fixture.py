"""Public encoder fixture for exactly Gate, Up, SiLU multiply and Down.

This is FFN4, not a skipped-prefix execution of the 21-command full block.
Only metadata bytes are built here; reconstructible numeric payloads stay local.
"""
from dataclasses import dataclass
from math import prod
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))
from heteronpu.command import Command128, Engine, Opcode
from heteronpu.descriptor_chain import DescriptorRecord, MatrixAux, SfuProgram, TensorDType
from heteronpu.gemmini_descriptor_v2 import tensor_base_record, shape4_record, stride3_record, matrix_op_record

try:
    from .model import LaunchConfig, MetadataMemory, NULL, Region, Table, align64
except ImportError:
    from model import LaunchConfig, MetadataMemory, NULL, Region, Table, align64


@dataclass
class Fixture:
    config: LaunchConfig
    memory: MetadataMemory
    commands: tuple
    records: tuple
    roots: tuple
    specs: dict
    scope: str = 'FFN4_COMMAND_SUBPROGRAM_ONLY'

    def physical_spans(self):
        spans = [(name, address, address + align64(prod(shape) * (2 if dtype == 5 else 4)))
                 for name, (address, shape, dtype) in self.specs.items()]
        spans += [('command_table', self.config.command.base, self.config.command.limit),
                  ('descriptor_table', self.config.descriptor.base, self.config.descriptor.limit),
                  ('workspace', self.config.regions[3].base, self.config.regions[3].limit)]
        return spans

    def validate_spans(self):
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
