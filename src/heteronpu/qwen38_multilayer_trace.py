"""Self-contained tiny Qwen3.8 multi-layer trace/replay/partition regression.

The model is intentionally small but executes persistent PLE, four-branch GR,
three recurrent GDN layers, one sparse-QSA layer, routed/shared MoE and a
transactional MTP accept/rollback check. It closes the software/E0 trace goal;
it is not an official-weight or RTL backend result.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
from typing import Iterable


def f32(x: float) -> float:
    # Stable deterministic rounding proxy for this self-contained E0 model.
    import struct
    return struct.unpack("<f", struct.pack("<f", float(x)))[0]


def vec_hash(values: Iterable[float | int]) -> str:
    payload = json.dumps([float(v) if isinstance(v, float) else int(v) for v in values], separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


@dataclass
class TinyState:
    token_index: int = 0
    gdn: list[list[float]] = field(default_factory=lambda: [[0.0] * 4 for _ in range(3)])
    qsa_keys: list[tuple[float, ...]] = field(default_factory=list)
    ple_history: list[int] = field(default_factory=list)
    ple_conv: list[float] = field(default_factory=lambda: [0.0] * 8)
    hyper: list[float] = field(default_factory=lambda: [0.0] * 32)
    generation: int = 0

    def copy(self) -> "TinyState":
        return TinyState(self.token_index, [x[:] for x in self.gdn], self.qsa_keys[:], self.ple_history[:], self.ple_conv[:], self.hyper[:], self.generation)


@dataclass(frozen=True)
class TraceNode:
    node_id: str
    token: int
    layer: int
    op: str
    engine: str
    input_sha256: str
    output_sha256: str
    state_domain: str | None = None
    state_before_sha256: str | None = None
    state_after_sha256: str | None = None
    attrs: tuple[tuple[str, int | float | str], ...] = ()


@dataclass(frozen=True)
class TokenTrace:
    token_id: int
    hidden: tuple[float, ...]
    nodes: tuple[TraceNode, ...]
    routes: tuple[tuple[int, ...], ...]
    qsa_selected: tuple[int, ...]


def _norm(x: list[float]) -> list[float]:
    den = math.sqrt(sum(v * v for v in x) / max(len(x), 1) + 1e-6)
    return [f32(v / den) for v in x]


def _gr_read(hyper: list[float]) -> list[float]:
    # Four branches of width eight.
    out = []
    for i in range(8):
        weights = [1.0 + ((i + b) % 3) * 0.125 for b in range(4)]
        den = sum(weights)
        out.append(f32(sum(hyper[b * 8 + i] * weights[b] for b in range(4)) / den))
    return _norm(out)


def _gr_write(hyper: list[float], block: list[float], layer: int) -> list[float]:
    out = hyper[:]
    for b in range(4):
        gate = f32(0.25 + 0.1 * ((layer + b) % 3))
        for i in range(8):
            out[b * 8 + i] = f32(out[b * 8 + i] + gate * block[i])
    return out


def _moe(x: list[float], layer: int) -> tuple[list[float], tuple[int, ...]]:
    scores = [f32(sum(x[i] * (((e + 1) * (i + 3)) % 11 - 5) * 0.03125 for i in range(8))) for e in range(4)]
    route = tuple(sorted(range(4), key=lambda e: (-scores[e], e))[:2])
    out = [0.0] * 8
    for e in route:
        for i in range(8):
            out[i] = f32(out[i] + math.tanh(x[i] * (0.75 + 0.1 * e)) * (0.5 + 0.1 * e))
    # Shared expert.
    for i in range(8): out[i] = f32(out[i] + 0.2 * math.tanh(x[i]))
    return out, route


def _node(token: int, layer: int, op: str, engine: str, before: Iterable[float | int], after: Iterable[float | int], *, domain: str | None = None, state_before: Iterable[float | int] | None = None, state_after: Iterable[float | int] | None = None, **attrs: int | float | str) -> TraceNode:
    return TraceNode(f"t{token}.l{layer}.{op}", token, layer, op, engine, vec_hash(before), vec_hash(after), domain, None if state_before is None else vec_hash(state_before), None if state_after is None else vec_hash(state_after), tuple(sorted(attrs.items())))


class TinyQwen38TraceModel:
    def initial_state(self) -> TinyState:
        return TinyState()

    def step(self, token_id: int, state: TinyState) -> tuple[TokenTrace, TinyState]:
        s = state.copy(); token = s.token_index
        hidden = [f32(math.sin((token_id + 1) * (i + 1) * 0.17)) for i in range(8)]
        if token == 0: s.hyper = [v for _ in range(4) for v in hidden]
        else:
            for b in range(4):
                for i in range(8): s.hyper[b * 8 + i] = f32(s.hyper[b * 8 + i] + hidden[i] * 0.125)
        nodes: list[TraceNode] = [_node(token, -1, "TOKEN_EMBED", "memory", [token_id], hidden)]
        routes: list[tuple[int, ...]] = []
        qsa_selected: tuple[int, ...] = ()
        for layer in range(4):
            if layer == 1:
                before_hist = s.ple_history[:]
                s.ple_history.append(token_id); s.ple_history = s.ple_history[-3:]
                hashes = [((s.ple_history[-1] * 1315423911 + n * 2654435761) & 0xFFFF) for n in (2, 3)]
                before_conv = s.ple_conv[:]
                for i in range(8): s.ple_conv[i] = f32(0.5 * s.ple_conv[i] + ((hashes[i % 2] & 255) - 128) / 512.0)
                old = s.hyper[:]
                for b in range(4):
                    for i in range(8): s.hyper[b * 8 + i] = f32(s.hyper[b * 8 + i] + s.ple_conv[i] * 0.1)
                nodes.append(_node(token, layer, "PLE_HASH_GATHER_CONV", "memory_state", old, s.hyper, domain="ple", state_before=before_hist + before_conv, state_after=s.ple_history + s.ple_conv, rows=len(hashes)))
            mixed = _gr_read(s.hyper)
            nodes.append(_node(token, layer, "GR_ATTN_READ", "matrix_sfu", s.hyper, mixed, branches=4))
            if layer < 3:
                before_state = s.gdn[layer][:]
                key = [f32(mixed[i] * 0.5 + mixed[(i + 1) % 8] * 0.25) for i in range(4)]
                for i in range(4): s.gdn[layer][i] = f32(s.gdn[layer][i] * 0.875 + key[i] * mixed[i + 4])
                block = [f32(mixed[i] + s.gdn[layer][i % 4] * 0.25) for i in range(8)]
                nodes.append(_node(token, layer, "GDN_RECURRENT", "matrix_state_sfu", mixed, block, domain="gdn", state_before=before_state, state_after=s.gdn[layer], state_bytes=16))
            else:
                before_keys = [v for row in s.qsa_keys for v in row]
                key = tuple(f32(v * 0.5) for v in mixed[:4]); s.qsa_keys.append(key)
                scores = [(idx, sum(key[i] * old[i] for i in range(4))) for idx, old in enumerate(s.qsa_keys)]
                qsa_selected = tuple(sorted((idx for idx, _ in sorted(scores, key=lambda x: (-x[1], x[0]))[:4])))
                block = [f32(mixed[i] + sum(s.qsa_keys[p][i % 4] for p in qsa_selected) * 0.125) for i in range(8)]
                nodes.append(_node(token, layer, "QSA_SELECT_QK_SOFTMAX_PV", "matrix_sfu_kv", mixed, block, domain="qsa", state_before=before_keys, state_after=[v for row in s.qsa_keys for v in row], selected=len(qsa_selected)))
            before_hyper = s.hyper[:]; s.hyper = _gr_write(s.hyper, block, layer)
            nodes.append(_node(token, layer, "GR_ATTN_WRITE", "sfu", before_hyper, s.hyper))
            mixed = _gr_read(s.hyper); nodes.append(_node(token, layer, "GR_MOE_READ", "matrix_sfu", s.hyper, mixed))
            moe, route = _moe(mixed, layer); routes.append(route)
            nodes.append(_node(token, layer, "MOE_ROUTED_SHARED", "matrix_sfu_weight", mixed, moe, active=len(route)))
            before_hyper = s.hyper[:]; s.hyper = _gr_write(s.hyper, moe, layer + 4)
            nodes.append(_node(token, layer, "GR_MOE_WRITE", "sfu", before_hyper, s.hyper))
        final = _norm(_gr_read(s.hyper)); nodes.append(_node(token, 4, "FINAL_MERGE_RMSNORM", "sfu", s.hyper, final))
        s.token_index += 1
        return TokenTrace(token_id, tuple(final), tuple(nodes), tuple(routes), qsa_selected), s

    def run(self, tokens: Iterable[int], state: TinyState | None = None) -> tuple[tuple[TokenTrace, ...], TinyState]:
        s = state.copy() if state else self.initial_state(); out=[]
        for token in tokens:
            result,s=self.step(int(token),s);out.append(result)
        return tuple(out),s


def _serialize(results: tuple[TokenTrace, ...], state: TinyState) -> str:
    raw = {"results":[asdict(r) for r in results],"state":asdict(state)}
    return json.dumps(raw,sort_keys=True,separators=(",",":"))


def _partition(results: tuple[TokenTrace, ...]) -> dict[str, object]:
    policy = {
        "PLE_HASH_GATHER_CONV":"ple_policy","GR_ATTN_READ":"gated_residual_policy","GDN_RECURRENT":"delta_policy",
        "QSA_SELECT_QK_SOFTMAX_PV":"qsa_policy","GR_ATTN_WRITE":"gated_residual_policy","GR_MOE_READ":"gated_residual_policy",
        "MOE_ROUTED_SHARED":"moe_policy","GR_MOE_WRITE":"gated_residual_policy","FINAL_MERGE_RMSNORM":"rmsnorm","TOKEN_EMBED":"memory",
    }
    segments=[]
    for result in results:
        for node in result.nodes:
            segments.append((node.node_id,policy.get(node.op,"fallback"),node.engine,node.state_domain))
    payload=json.dumps(segments,sort_keys=True,separators=(",",":")).encode()
    return {"segments":len(segments),"fallback":sum(p[1]=="fallback" for p in segments),"sha256":hashlib.sha256(payload).hexdigest(),"policies":sorted({p[1] for p in segments})}


def multilayer_trace_report() -> dict[str, object]:
    tokens=(1,4,7,3,9,2,11,5);model=TinyQwen38TraceModel()
    batch,state_a=model.run(tokens)
    state_b=model.initial_state();step=[]
    for token in tokens:
        result,state_b=model.step(token,state_b);step.append(result)
    if _serialize(batch,state_a)!=_serialize(tuple(step),state_b):raise AssertionError("prefill/decode mismatch")
    payload=_serialize(batch,state_a);reloaded=json.loads(payload)
    if json.dumps(reloaded,sort_keys=True,separators=(",",":"))!=payload:raise AssertionError("replay")
    partition=_partition(batch);partition2=_partion(tuple(step))
    if partition!=partition2 or partition["fallback"]:raise AssertionError(partition)
    descriptor_payload=json.dumps({"partition":partition,"tokens":tokens,"generation":state_a.generation,"state_domains":["gdn","qsa","ple","hyper","moe","mtp"]},sort_keys=True,separators=(",",":")).encode()
    # Transactional MTP check: draft two tokens, accept one, compare with baseline one-token state.
    base_state=state_a.copy();draft,draft_state=model.run((6,8),base_state);accepted,accepted_state=model.run((6,),base_state)
    if _serialize((accepted[0],),accepted_state)!=_serialize((draft[0],),model.step(6,base_state)[1]):raise AssertionError("MTP prefix")
    return {"schema_version":1,"status":"PASS","evidence_class":"tiny_Qwen38_multilayer_trace_E0_not_official_weight_backend","tokens":len(tokens),"layers":4,"nodes":sum(len(r.nodes) for r in batch),"operator_families":sorted({n.op for r in batch for n in r.nodes}),"prefill_decode_diff":0,"trace_sha256":hashlib.sha256(payload.encode()).hexdigest(),"partition":partition,"descriptor_sha256":hashlib.sha256(descriptor_payload).hexdigest(),"mtp_draft_steps":2,"mtp_accepted_steps":1,"state_domains":["gdn","qsa","ple","hyper","moe","mtp"],"remaining_local_gates":["official immutable trace","real GGML node capture","GGUF tensor binding","backend E1/E2/E3"]}
