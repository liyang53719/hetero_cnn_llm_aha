"""Hardware-oriented executable micro-op schedule for Qwen3.8-Flash-Next text layers."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class MicroOp:
    op_id: int
    layer: int
    name: str
    engine: str
    depends_on: tuple[int, ...]
    stateful: bool = False
    e0_executable: bool = True
    rtl_executable: bool = False


@dataclass(frozen=True)
class Schedule:
    micro_ops: tuple[MicroOp, ...]

    def validate(self) -> None:
        ids = {op.op_id for op in self.micro_ops}
        if len(ids) != len(self.micro_ops):
            raise ValueError('duplicate op id')
        seen: set[int] = set()
        for op in self.micro_ops:
            if any(dep not in ids for dep in op.depends_on):
                raise ValueError(f'missing dependency for {op.name}')
            if any(dep not in seen for dep in op.depends_on):
                raise ValueError(f'non-topological dependency for {op.name}')
            seen.add(op.op_id)

    @property
    def operator_names(self) -> frozenset[str]:
        return frozenset(op.name for op in self.micro_ops)

    def local_dependencies(self) -> tuple[MicroOp, ...]:
        return tuple(op for op in self.micro_ops if not op.rtl_executable)


def build_qwen38_schedule(layer_pattern: Iterable[str], ple_layer_ids: Iterable[int] = (1,), include_mtp: bool = True) -> Schedule:
    ple_layers = set(int(x) for x in ple_layer_ids)
    ops: list[MicroOp] = []
    next_id = 0
    previous: tuple[int, ...] = ()

    def emit(layer: int, name: str, engine: str, *, stateful: bool = False, rtl: bool = False, deps: tuple[int, ...] | None = None) -> int:
        nonlocal next_id, previous
        dependencies = previous if deps is None else deps
        op = MicroOp(next_id, layer, name, engine, dependencies, stateful, True, rtl)
        ops.append(op)
        previous = (next_id,)
        next_id += 1
        return op.op_id

    emit(-1, 'TOKEN_EMBED', 'memory', rtl=False)
    for layer, layer_type in enumerate(tuple(layer_pattern)):
        if layer in ple_layers:
            emit(layer, 'PLE_NGRAM_HASH_LOOKUP', 'state', stateful=True)
            emit(layer, 'PLE_KEY_VALUE_PROJECTION', 'matrix')
            emit(layer, 'PLE_GATE_DILATED_DWCONV', 'sfu_state', stateful=True)
        emit(layer, 'GR_ATTN_READ', 'matrix_sfu')
        if layer_type == 'linear_attention':
            emit(layer, 'GDN_INPUT_PROJECTIONS', 'matrix')
            emit(layer, 'GDN_CAUSAL_CONV', 'state', stateful=True)
            emit(layer, 'GDN_RECURRENT_STATE_UPDATE', 'matrix_state', stateful=True)
            emit(layer, 'GDN_GATED_NORM_OUT_PROJ', 'matrix_sfu')
        elif layer_type == 'qwen_sparse_attention':
            emit(layer, 'QSA_INDEX_PROJECTION', 'matrix')
            emit(layer, 'QSA_COMPRESS_TOPK', 'sfu_state', stateful=True)
            emit(layer, 'SPARSE_QKV_PROJECTION', 'matrix')
            emit(layer, 'SPARSE_QK_ONLINE_SOFTMAX_PV', 'matrix_sfu_kv', stateful=True)
            emit(layer, 'ATTENTION_OUTPUT_GATE_PROJECTION', 'matrix_sfu')
        else:
            raise ValueError(f'unsupported layer type {layer_type}')
        emit(layer, 'GR_ATTN_WRITE', 'sfu')
        emit(layer, 'GR_MOE_READ', 'matrix_sfu')
        emit(layer, 'MOE_ROUTER_TOPK', 'sfu')
        emit(layer, 'MOE_ROUTED_EXPERT_GEMM', 'matrix_weight_cache')
        emit(layer, 'MOE_SHARED_EXPERT', 'matrix_sfu')
        emit(layer, 'GR_MOE_WRITE', 'sfu')
    emit(len(tuple(layer_pattern)), 'FINAL_HYPER_MERGE_RMSNORM', 'sfu')
    if include_mtp:
        emit(len(tuple(layer_pattern)), 'MTP_DRAFT_BLOCK', 'matrix_sfu_state', stateful=True)
        emit(len(tuple(layer_pattern)), 'MTP_TARGET_VERIFY', 'control_state', stateful=True)
        emit(len(tuple(layer_pattern)), 'MTP_STATE_COMMIT_ROLLBACK', 'state', stateful=True)
    schedule = Schedule(tuple(ops))
    schedule.validate()
    return schedule
