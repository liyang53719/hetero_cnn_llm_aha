"""Parameter-only adaptation of existing public3 synthetic Attention fixture."""
from candidates.qwen2_resident_matrix.ffn_public import fixture as f,model

def attention_fixture(rows=8):
    if type(rows) is not int or rows not in (1,2,8,16):raise ValueError("synthetic fixture rows")
    specs = dict(q=(0x1000000, (rows, 1536), 7), k=(0x2000000, (rows, 256), 7),
                 v=(0x3000000, (rows, 256), 7), scores=(0x8000000, (12, rows, rows), 7),
                 probabilities=(0x9000000, (12, rows, rows), 7), att=(0xa000000, (rows, 1536), 7))
    records, commands, roots = [], [], []

    def chain(name, extra=()):
        address, shape, dtype = specs[name]
        dims, root = shape + (1,) * (4 - len(shape)), len(records)
        records.extend((f.tensor_base_record(address, dtype=dtype, rank=len(shape), next_index=root + 1),
            f.shape4_record(dims, next_index=root + 2),
            f.stride3_record((dims[1] * dims[2] * dims[3], dims[2] * dims[3], dims[3]),
                            next_index=root + 3 if extra else f.NULL)))
        for index, record in enumerate(extra):
            records.append(f.DescriptorRecord(record.record_type, record.subtype, record.flags,
                root + 4 + index if index + 1 < len(extra) else f.NULL, record.payload))
        return root

    for opcode, a, b, dst, extra in (
        (f.Opcode.MATRIX_QK, 'q', 'k', 'scores',
         (f.matrix_op_record(m=rows, n=rows, k=128, dataflow=0, transpose_b=True), f.MatrixAux(full_c=True).to_record())),
        (f.Opcode.SFU_SOFTMAX, 'scores', None, 'probabilities',
         (f.SfuProgram(0x33, 1, input_dtype=f.TensorDType.FP32, output_dtype=f.TensorDType.FP32).to_record(),)),
        (f.Opcode.MATRIX_PV, 'probabilities', 'v', 'att',
         (f.matrix_op_record(m=rows, n=128, k=rows, dataflow=0), f.MatrixAux(full_c=True).to_record()))):
        root = chain(a, extra), chain(b) if b else f.NULL, chain(dst)
        pc = len(commands)
        commands.append(f.Command128(opcode, f.Engine.SFU_CGRA if b is None else f.Engine.MATRIX,
            event_wait=pc, event_signal=pc + 1, src0=root[0], src1=root[1], dst=root[2]))
        roots.append(root)
    cb = b''.join(command.to_bytes() for command in commands)
    db = b''.join(record.pack().to_bytes(16, 'little') for record in records)
    ct = model.Table(0xc000000, 0xc000000 + model.align64(len(cb)), len(commands))
    dt = model.Table(0xc001000, 0xc001000 + model.align64(len(db)), len(records))
    regions = (model.Region(0x1000000, 0x8000000, True, False),
               model.Region(0x8000000, 0xc000000, True, True),
               model.Region(0xc000000, 0xc010000, True, False),
               model.Region(0x10000000, 0x100c0000, True, True))
    config = model.LaunchConfig(ct, dt, regions)
    metadata = model.MetadataMemory(((ct.base, cb.ljust(model.align64(len(cb)), b'\0')),
                                    (dt.base, db.ljust(model.align64(len(db)), b'\0'))))
    allocations = {}
    for name, (address, shape, dtype) in specs.items():
        words = 1
        for dimension in shape:
            words *= dimension
        allocations[name] = f.PhysicalAllocation(address, shape, dtype, model.align64(words * 4),
            name in ('q', 'k', 'v'), name in ('scores', 'probabilities'))
    fixture = f.Fixture(config, metadata, tuple(commands), tuple(records), tuple(roots), specs,
                        scope='SYNTHETIC_M%d_PUBLIC_ATTENTION_ONLY'%rows, allocations=allocations)
    fixture.validate_spans()
    return fixture
