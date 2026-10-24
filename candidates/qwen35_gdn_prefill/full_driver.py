"""Typed SOFTWARE coordinator for the complete Qwen3.5-0.8B L0 GDN block.

One byte map, DenseOwner/Matrix facade, selected shared Scalar and Vector16 serve every
owner. Only raw inputs/constants are loaded before launch. No reference or
native forward is imported here. This is not a public Command128 decoder,
RTL implementation, hardware timing model, or numerical acceptance oracle.

Chunk core becomes a readable intermediate after its actual staging receipt.
Conv history and recurrent FP32 state remain private through the whole FFN.
The final residual terminal is held until a joint fence can publish both
roots and the output, advancing the generation once. A carried invocation
can consume only this coordinator's preceding actual committed root pair.
"""
from __future__ import annotations

import argparse
import ctypes as C
from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json
import os
import struct
from pathlib import Path
import time
from typing import NamedTuple

import numpy as np

from . import typed_dense as d, rms_owner as rms
from .conv import model as conv
from .prep import model as prep
from .chunk import model as chunk
from .chunk.vector import (Vector16, LEGACY_POLICY, IEEE_POLICY, POLICY_MASKS,
                           LEGACY_BACKEND, ARITHMETIC_BACKENDS, verify_library)
from .gated_norm import model as norm
from .elementwise import model as elt
from .dense_prefix import TypedSeededDenseDriver
from .scalar_identity import (ScalarIdentityGuard, SCALAR_SOURCE_FILES, FULL_ARITHMETIC_SEAL_SCHEMA,
                              chunk_exp_routing_identity, chunk_exp_dispatch_identity)


SCOPE = 'QWEN35_L0_COMPLETE_TYPED_SOFTWARE_COORDINATOR'
ORDER = ('input_norm', 'qkv', 'z', 'ab', 'conv_silu', 'prep', 'chunk',
         'gated_norm', 'o', 'attention_residual', 'post_norm', 'gate', 'up',
         'silu_mul', 'down', 'output')
DENSE = {'qkv': (1024, 6144), 'z': (1024, 2048), 'ab': (1024, 32),
         'o': (2048, 1024), 'gate': (1024, 3584), 'up': (1024, 3584),
         'down': (3584, 1024)}


class ProjectionPolicy(str, Enum):
    Legacy = 'legacy_sequential_k'
    IndependentK512 = 'gdn_pair_k512_independent_fp32_sum'


ACTUAL_SOURCE_FILES = (
    'candidates/qwen35_gdn_prefill/full_driver.py',
    'candidates/qwen35_gdn_prefill/typed_dense.py',
    'candidates/qwen35_gdn_prefill/dense_prefix.py',
    'candidates/qwen35_gdn_prefill/rms_owner.py',
    'candidates/qwen35_gdn_prefill/conv/model.py',
    'candidates/qwen35_gdn_prefill/conv/scalar.py',
    'candidates/qwen35_gdn_prefill/prep/model.py',
    'candidates/qwen35_gdn_prefill/prep/scalar.py',
    'candidates/qwen35_gdn_prefill/prep/layout.py',
    'candidates/qwen35_gdn_prefill/prep/reduction.py',
    'candidates/qwen35_gdn_prefill/chunk/model.py',
    'candidates/qwen35_gdn_prefill/chunk/exp_policy.py',
    'candidates/qwen35_gdn_prefill/chunk/cumsum.py',
    'candidates/qwen35_gdn_prefill/chunk/matmul_reuse.py',
    'candidates/qwen35_35b_exp/gate_scalar.py',
    'candidates/qwen35_gdn_prefill/chunk/vector.py',
    'candidates/qwen35_gdn_prefill/chunk/vector16.cpp',
    'candidates/qwen35_gdn_prefill/gated_norm/model.py',
    'candidates/qwen35_gdn_prefill/elementwise/model.py',
    'candidates/qwen2_resident_matrix/transposed_down/model.py',
    'candidates/qwen2_resident_matrix/ffn_attention/matrix_service.py',
    'scripts/build_shared_matrix_recipe.py',
    'src/heteronpu/model_geometry.py',
) + SCALAR_SOURCE_FILES
WEIGHTS = {'qkv': 'linear_attn.in_proj_qkv.weight', 'z': 'linear_attn.in_proj_z.weight',
           'o': 'linear_attn.out_proj.weight', 'gate': 'mlp.gate_proj.weight',
           'up': 'mlp.up_proj.weight', 'down': 'mlp.down_proj.weight'}


def require(ok, why):
    if not ok:
        raise ValueError('typed full block: ' + why)


def _validate_chunk_exp_policy(policy, vector):
    chunk_exp_routing_identity(chunk.ep)
    require(type(policy) is str and policy in
            (chunk.ep.LEGACY_EXP, chunk.ep.EQUAL_HEADS_EXPERIMENTAL_EXP),
            'explicit legacy or EQUAL_HEADS_EXPERIMENTAL_EXP chunk policy required')
    if policy == chunk.ep.EQUAL_HEADS_EXPERIMENTAL_EXP:
        require(type(vector) is Vector16 and vector.exception_policy == chunk.ep.IEEE_POLICY and
                type(vector.fatal_mask) is int and vector.fatal_mask == 28,
                'experimental equal-head chunk exp requires explicit IEEE Vector mask 28')


def _new_chunk_scalar(policy, vector):
    _validate_chunk_exp_policy(policy, vector)
    if policy == chunk.ep.EQUAL_HEADS_EXPERIMENTAL_EXP:
        return chunk.ep.DecayScalar(enable_softplus=True, enable_ieee_exp=True)
    return prep.PrepScalar(enable_softplus=True)


def _admit_chunk_scalar(policy, vector, scalar):
    _validate_chunk_exp_policy(policy, vector)
    if policy == chunk.ep.LEGACY_EXP:
        require(type(scalar) is prep.PrepScalar and scalar.enable_softplus is True,
                'one explicitly Softplus-enabled PrepScalar required')
    else:
        require(type(scalar) is chunk.ep.DecayScalar and scalar.enable_softplus is True and
                scalar.enable_ieee_exp is True,
                'one exact explicitly enabled DecayScalar with literal boolean flags required')
    guard = ScalarIdentityGuard(scalar)
    chunk.ep.validate_policy(policy, chunk.EQUAL_HEADS, scalar, vector)
    return guard


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def status(response):
    return response[1] if type(response) is tuple else response.status


def complete_region(memory, region, *, published=False):
    require(memory.regions.get(region.base) is region and not region.readonly and
            region.published is published, 'staging allocation identity/publication changed')
    region.check()
    require(region.written == region.acknowledged == set(range(0, region.extent, 64)),
            'incomplete physical write/final ACK coverage')


@dataclass(frozen=True)
class CommittedRoots:
    generation: int = 0
    history: int | None = None
    state: int | None = None
    output: int | None = None
    history_sha256: str | None = None
    state_sha256: str | None = None


@dataclass(frozen=True)
class FullBlockResult:
    phase: str
    status: str | None
    generation: int
    output: int | None
    history: int | None
    state: int | None
    failed_role: str | None = None


class FullBlockProgress(NamedTuple):
    """Detached telemetry only, never an owner receipt or numerical evidence.

    Elapsed time is relative to this window's start; ticks and terminal count
    are coordinator totals. Chunk head/subchunk are zero-based and may be None.
    Every field is an exact immutable primitive, never a live model handle.
    """
    phase: str
    role: str
    ticks: int
    owner_state: str | None
    owner_ticks: int | None
    chunk_phase: str | None
    chunk_head: int | None
    chunk_subchunk: int | None
    generation: int
    terminal_count: int
    elapsed_seconds: float


class FullBlockCoordinator:
    """Caller-driven sequential owner transport, with no arithmetic replacement.

    ``inputs`` maps phase names to complete M16 or M128 BF16 hidden bytes.
    ``vector`` is explicitly provided, preserving its selected numerical policy.
    ``observe(phase, role, report, outputs)`` receives real bytes only after an
    owner terminal; state/history entries are explicitly named ``*_staging``.
    The output callback happens after the joint commit. Tick keyword arguments
    are forwarded to the active owner transport; reset requests mean abort and
    drain. Call reset() only after the failed block terminal has been consumed.
    """
    def __init__(self, weights, inputs, *, matrix, vector, memory=None, dense=None,
                 scalar=None, rms_policy=rms.ReductionPolicy.Torch210CpuDefault1024,
                 projection_policy=ProjectionPolicy.Legacy, observe=None,
                 chunk_exp_policy=chunk.ep.LEGACY_EXP):
        require(type(matrix) is d.MatrixService and type(vector) is Vector16,
                'explicit shared MatrixService and Vector16 required')
        vector.arithmetic_identity()
        self.memory = d.TypedMemory() if memory is None else memory
        require(type(self.memory) is d.TypedMemory and self.memory.pending is None,
                'one drained TypedMemory required')
        self.matrix, self.vector = matrix, vector
        require(vector.exception_policy in POLICY_MASKS and
                vector.fatal_mask == POLICY_MASKS[vector.exception_policy],
                'explicit coherent Vector exception policy required')
        self.chunk_exp_policy = chunk_exp_policy
        self.scalar = _new_chunk_scalar(chunk_exp_policy, vector) if scalar is None else scalar
        self._scalar_guard = _admit_chunk_scalar(chunk_exp_policy, vector, self.scalar)
        self.projection_policy = ProjectionPolicy(projection_policy)
        self.projection_module = self.projection_profile = None
        if self.projection_policy is ProjectionPolicy.IndependentK512:
            from . import projection_driver, projection_owner
            self.projection_module = projection_driver
            self.projection_profile = projection_driver.GDN_PROJECTION_PROFILE
            self.dense = projection_owner.GdnProjectionOwner() if dense is None else dense
            require(type(self.dense) is projection_owner.GdnProjectionOwner,
                    'explicit GDN projection owner required by selected policy')
        else:
            self.dense = d.down.DenseOwnerModel() if dense is None else dense
            require(type(self.dense) is d.down.DenseOwnerModel, 'legacy exact Down owner required')
        self.dense_wire = d.dense_wire_authority(self.dense, d.down.Job())
        # Concrete transport adapters still enforce their own supported owner protocol.
        require(self.dense.state == 'idle' and
                not self.dense.error and matrix.owner is None and not matrix.reset_required and
                self.scalar.client is None and vector.client is None, 'drained resources required')
        self.rms = rms.RmsOwner(self.scalar)
        self.conv_nodes = {}
        self.conv = conv.ConvOwner(self.scalar, observe=self._observe_conv)
        self.prep = prep.InputPrepOwner(self.scalar)
        self.chunk = chunk.ChunkOwner(self.scalar, vector, host_batch=True,
                                      exp_policy=self.chunk_exp_policy)
        self.norm = norm.GatedNormOwner(self.scalar)
        self.elementwise = elt.ElementwiseOwner(self.scalar)
        self.policy, self.observe = rms.ReductionPolicy(rms_policy), observe
        self._next_address = max([0x100000, *(r.base + r.extent + 64 for r in self.memory.regions.values())])
        self.parameters = {}
        # Parameters retain their original storage types. Dense only changes
        # the byte layout from checkpoint [N,K] to the owner's physical [K,N].
        for role, (k, n) in DENSE.items():
            raw = (weights['linear_attn.in_proj_a.weight'] + weights['linear_attn.in_proj_b.weight']
                   if role == 'ab' else weights[WEIGHTS[role]])
            require(type(raw) is bytes and len(raw) == k * n * 2, role + ' BF16 parameter extent')
            packed = np.frombuffer(raw, '<u2').reshape(n, k).T.copy().tobytes()
            self.parameters[role] = self._allocate(len(packed), raw=packed)
        for role, name, extent in (
                ('input_norm', 'input_layernorm.weight', 2048),
                ('post_norm', 'post_attention_layernorm.weight', 2048),
                ('conv', 'linear_attn.conv1d.weight', 6144 * 8),
                ('gated_norm', 'linear_attn.norm.weight', 128 * 4),
                ('a_log', 'linear_attn.A_log', 64), ('dt_bias', 'linear_attn.dt_bias', 32)):
            raw = weights[name]
            require(type(raw) is bytes and len(raw) == extent, role + ' original parameter extent')
            self.parameters[role] = self._allocate((extent + 63) // 64 * 64,
                                                  raw=raw + bytes((-extent) % 64))
        require(bool(inputs), 'at least one prelaunch raw input required')
        self.plans = {}
        for phase, raw in inputs.items():
            require(type(phase) is str and phase and type(raw) is bytes and
                    len(raw) in (16 * 2048, 128 * 2048), 'named raw M16/M128 hidden input')
            rows = len(raw) // 2048
            plan = {'rows': rows, 'hidden': self._allocate(len(raw), raw=raw)}
            sizes = {name: rows * n * 2 for name, (_, n) in DENSE.items()}
            sizes.update(input_norm=rows * 2048, conv_silu=rows * 12288,
                         prep=rows * prep.CORE_ROW_BYTES, chunk=rows * 4096,
                         gated_norm=rows * 4096, attention_residual=rows * 2048,
                         post_norm=rows * 2048, silu_mul=rows * 7168, output=rows * 2048,
                         history=6144 * 8, state=16 * 128 * 128 * 4,
                         prefix=1024 // 32 * 16384)
            for name, extent in sizes.items():
                plan[name] = self._allocate(extent)
            sizing = chunk.ChunkJob(0, 0, 0, 0, 0, 0, rows, exp_policy=self.chunk_exp_policy)
            plan['scratch'] = self._allocate(sizing.scratch_bytes)
            self.plans[phase] = plan
        self.cold_history = self._allocate(6144 * 8)
        self.cold_state = self._allocate(16 * 128 * 128 * 4)
        self.readonly_hashes = {r.base: sha(r.raw()) for r in self.memory.regions.values() if r.readonly}
        self.allocations = {base: r for base, r in self.memory.regions.items()}
        self.resource_identity = self._resource_identity()
        self.roots = CommittedRoots()
        self.active = self.response = self.phase = self.role = None
        self._index, self._tag, self.ticks = 0, 1, 0
        self.locked = self.aborted = False
        self.launched, self.commands, self.receipts = set(), [], {}
        self.producer_hashes = {}
        self.window_inputs = []

    def _observe_conv(self, tag, token, channel, bits):
        slot = self.conv_nodes[tag]
        index = token * 6144 + channel
        require(type(token) is int and type(channel) is int and type(bits) is int and
                0 <= token < slot['rows'] and 0 <= channel < 6144 and 0 <= bits < 65536 and
                not slot['seen'][index], 'invalid/duplicate actual Conv pre-SiLU observation')
        struct.pack_into('<H', slot['data'], index * 2, bits)
        slot['seen'][index] = 1
        slot['count'] += 1

    def _conv_observation(self, tag):
        slot = self.conv_nodes[tag]
        return dict(observed=slot['count'], expected=len(slot['seen']),
                    complete=slot['count'] == len(slot['seen']) and all(slot['seen']),
                    seen_sha256=sha(bytes(slot['seen'])), output_sha256=sha(bytes(slot['data'])),
                    source='actual_ConvOwner_readonly_node_callback', numerical_replacement=False)

    def _allocate(self, extent, *, raw=None):
        base = (self._next_address + 63) // 64 * 64
        region = (self.memory.allocate_output(base, extent) if raw is None else
                  self.memory.add_readonly(base, raw))
        self._next_address = base + extent + 64
        return region.base

    def _resource_identity(self):
        return (id(self.memory), id(self.matrix), id(self.dense), id(self.dense.a_banks),
                id(self.dense.b_banks), self.matrix.resource_address, id(self.scalar),
                id(self.vector), self.vector.resource_address,
                self.vector.arithmetic_identity(), self._scalar_guard.check(self.scalar),
                chunk_exp_dispatch_identity(self.chunk),
                self.chunk_exp_policy, self.chunk.exp_policy, self.chunk.layout,
                self.chunk.cumsum_policy, self.chunk.matmul_policy, self.prep.layout,
                self.prep.gate_policy, self.prep.reduction_policy,
                self.vector.exception_policy, self.vector.fatal_mask, self.policy,
                self.projection_policy, self.projection_profile, id(self.projection_module), id(self.dense_wire),
                *(id(owner) for owner in (self.rms, self.conv, self.prep, self.chunk,
                                           self.norm, self.elementwise)))

    def _check_resources(self):
        require(self.resource_identity == self._resource_identity() and
                self.matrix.resource_address == self.matrix.lib.matrix_accumulator_address(),
                'shared owner/bank/service replaced')
        require(set(self.memory.regions) == set(self.allocations) and
                all(self.memory.regions.get(base) is region for base, region in self.allocations.items()),
                'physical allocation replaced or added after prelaunch')
        require(all(owner.scalar is self.scalar for owner in (self.rms, self.conv, self.prep,
                    self.chunk, self.norm, self.elementwise)) and self.chunk.vector is self.vector and
                self.chunk.host_batch is True and self.chunk.geometry == (16, 128, 128),
                'shared Scalar/Vector routing or full geometry changed')

    def _check_roots(self):
        roots = self.roots
        require(roots is self.window_roots, 'generation/root pair changed during invocation')
        if roots.generation:
            for base, digest in ((roots.history, roots.history_sha256), (roots.state, roots.state_sha256)):
                region = self.memory.regions[base]
                complete_region(self.memory, region, published=True)
                require(sha(region.raw()) == digest, 'previous committed root bytes changed')

    def start(self, phase, *, cold, expected_generation):
        self._check_resources()
        require(self.active is None and (self.phase is None or self.response is not None) and
                not self.locked, 'previous invocation must retire; failed invocation requires reset')
        require(phase in self.plans and phase not in self.launched, 'fresh preallocated phase required')
        require(type(cold) is bool and type(expected_generation) is int and
                expected_generation == self.roots.generation < (1 << 32) - 1 and
                cold == (self.roots.generation == 0), 'exact cold/carried committed generation required')
        require(self.memory.pending is None and self.matrix.owner is None and
                not self.matrix.reset_required and self.scalar.client is None and self.vector.client is None,
                'all shared services must be drained before block admission')
        self.window_roots = self.roots
        self._check_roots()
        self.phase, self.cold = phase, cold
        self.plan = self.plans[phase]
        for name, base in self.plan.items():
            if name not in ('rows', 'hidden'):
                region = self.memory.exact(base, self.memory.regions[base].extent, readable=False)
                require(region.raw() == d.GUARD * (region.extent // 64), 'intermediate lost initial sentinels')
        self.launched.add(phase)
        self.window_inputs.append(dict(phase=phase, cold=cold, expected_generation=expected_generation,
            history_sha256=self.window_roots.history_sha256, state_sha256=self.window_roots.state_sha256))
        self.active = self.response = None
        self.receipts, self._index, self.aborted = {}, 0, False
        self.role = ORDER[0]
        self._launch()

    def _launch(self):
        self._check_resources()
        p, w, tag = self.plan, self.parameters, self._tag
        require(tag < 1 << 32, 'owner tag exhausted')
        self._tag += 1
        role, rows = ORDER[self._index], p['rows']
        self.role = role
        if role in DENSE:
            k, n = DENSE[role]
            source = {'qkv': 'input_norm', 'z': 'input_norm', 'ab': 'input_norm',
                      'o': 'gated_norm', 'gate': 'post_norm', 'up': 'post_norm', 'down': 'silu_mul'}[role]
            require(self.dense.state == 'idle' and self.matrix.owner is None, 'workspace rebind while busy')
            self.dense.workspace = self.dense_wire.PrefixWorkspace(p['prefix'], 1024 // 32 * 16384,
                                                         self.window_roots.generation + 1)
            job = d.down.Job(m=rows, k=k, n=n, tag=tag, a=p[source], b=w[role], dst=p[role],
                            activation_bf16=True, weight_bf16=True, output_bf16=True,
                            write_bytes=rows * n * 2)
            if role in ('qkv', 'z', 'ab') and self.projection_profile is not None:
                self.active = self.projection_module.TypedProjectionDriver(
                    self.dense, self.matrix, self.memory, job, vector=self.vector,
                    role=role, profile=self.projection_profile)
            else:
                driver = TypedSeededDenseDriver if role == 'down' else d.TypedDenseDriver
                self.active = driver(self.dense, self.matrix, self.memory, job)
        elif role in ('input_norm', 'post_norm'):
            source = 'hidden' if role == 'input_norm' else 'attention_residual'
            self.active = rms.TypedRmsDriver(self.rms, self.memory,
                rms.RmsJob(tag, p[source], w[role], p[role], rows, self.policy))
        elif role == 'conv_silu':
            self.conv_nodes[tag] = dict(rows=rows, data=bytearray(rows * 6144 * 2),
                                        seen=bytearray(rows * 6144), count=0)
            history = self.cold_history if self.cold else self.window_roots.history
            self.active = conv.TypedConvDriver(self.conv, self.memory,
                conv.ConvJob(tag, p['qkv'], w['conv'], p[role], history, p['history'], rows,
                             self.cold, self.window_roots.generation),
                current_generation=self.window_roots.generation)
        elif role == 'prep':
            self.active = prep.TypedInputPrepDriver(self.prep, self.memory,
                prep.InputPrepJob(tag, p['conv_silu'], p['ab'], w['a_log'], w['dt_bias'], p[role], rows))
        elif role == 'chunk':
            previous = self.cold_state if self.cold else self.window_roots.state
            self.active = chunk.TypedChunkDriver(self.chunk, self.memory,
                chunk.ChunkJob(tag, p['prep'], previous, p['state'], p[role], p['scratch'], rows,
                               self.cold, self.window_roots.generation, exp_policy=self.chunk_exp_policy),
                current_generation=self.window_roots.generation,
                published_state_base=None if self.cold else previous)
        elif role == 'gated_norm':
            self.active = norm.TypedGatedNormDriver(self.norm, self.memory,
                norm.GatedNormJob(tag, p['chunk'], p['z'], w['gated_norm'], p[role], rows))
        else:
            a, b = {'attention_residual': ('hidden', 'o'), 'silu_mul': ('gate', 'up'),
                    'output': ('attention_residual', 'down')}[role]
            op = elt.ElementwiseOp.SiluMul if role == 'silu_mul' else elt.ElementwiseOp.Add
            self.active = elt.TypedElementwiseDriver(self.elementwise, self.memory,
                elt.ElementwiseJob(tag, p[a], p[b], p[role], rows, op,
                                   3584 if role == 'silu_mul' else 1024))

    def _preflight_commit(self, held):
        """All fallible checks precede accepting the final owner success."""
        self._check_resources()
        self._check_roots()
        p = self.plan
        require(status(held) is None and held.staging_complete and
                held.tag == self.active.job.tag and held.write_bytes == p['rows'] * 2048,
                'final success receipt identity/extent')
        require(self.memory.pending is None and self.active.pending is None and
                self.matrix.owner is None and not self.matrix.reset_required and
                self.scalar.client is None and self.vector.client is None,
                'full-block commit before all service/transport obligations retired')
        c, g = self.receipts['conv_silu'], self.receipts['chunk']
        require(c.status is None and c.staging_complete and not c.history_committed and
                c.generation == self.window_roots.generation and c.output_ack_bytes == p['rows'] * 12288 and
                c.history_ack_bytes == 6144 * 8 and g.status is None and g.staging_complete and
                g.expected_generation == self.window_roots.generation and g.state_out == p['state'] and
                g.output == p['chunk'] and g.state_bytes == 16 * 128 * 128 * 4 and
                g.output_bytes == p['rows'] * 4096 and not any((g.state_committed, g.history_committed,
                                                                           g.generation_advanced)),
                'actual Conv/chunk staging receipts required')
        regions = [self.memory.regions[p[name]] for name in ('history', 'state', 'output')]
        for region in regions:
            complete_region(self.memory, region)
        for base, digest in {**self.readonly_hashes, **self.producer_hashes}.items():
            require(sha(self.memory.regions[base].raw()) == digest, 'raw source/parameter/producer bytes changed')
        self._prepared_roots = CommittedRoots(self.window_roots.generation + 1, p['history'], p['state'],
                                              p['output'], sha(regions[0].raw()), sha(regions[1].raw()))

    def _commit(self):
        # Preflight ran on the exact held terminal immediately before the real
        # driver's acceptance. No callback or fallible operation splits this
        # software linearization point; final output was published by its owner.
        self.memory.regions[self.plan['history']].published = True
        self.memory.regions[self.plan['state']].published = True
        self.roots = self._prepared_roots
        self.response = FullBlockResult(self.phase, None, self.roots.generation,
                                        self.roots.output, self.roots.history, self.roots.state)

    def _fail(self, reason):
        self.locked = True
        self.response = FullBlockResult(self.phase, reason, self.roots.generation, None,
                                        self.roots.history, self.roots.state, self.role)

    def tick(self, *, abort=False, reset=False, **controls):
        require(self.phase is not None and self.response is None, 'no active block invocation')
        self._check_resources()
        self.ticks += 1
        self.aborted |= bool(abort or reset)
        if self.active is None:
            if self.aborted:
                self._fail('Aborted')
                return {}
            self._launch()
        driver = self.active
        held = driver.owner.ports()['response']
        accepting_output = (self.role == 'output' and held is not None and status(held) is None and
                            not self.aborted and controls.get('response_ready', True))
        if accepting_output:
            self._preflight_commit(held)
        event = driver.tick(abort=self.aborted, **controls)
        # Keep final owner acceptance -> joint commit free of fallible checks.
        # Other ticks may execute owner callbacks without producing a terminal.
        if not accepting_output:
            self._check_resources()
        if driver.response is None:
            return event
        self.receipts[self.role] = driver.response
        failed = status(driver.response)
        observation = self._conv_observation(driver.job.tag) if self.role == 'conv_silu' else None
        if observation is not None and failed is None and not self.aborted:
            require(observation['complete'], 'missing actual Conv pre-SiLU observations')
        if failed is None and not self.aborted:
            if self.role == 'chunk':
                # State is deliberately excluded from intermediate publication.
                self.memory.publish(self.plan['chunk'],
                                    (driver.response.tag, None, driver.job.output_bytes))
            if self.role == 'output':
                self._commit()
                self._check_resources()
        else:
            self._fail(failed or 'Aborted')
        report = driver.report()
        outputs = {}
        if observation is not None:
            report['conv_before_silu_observation'] = observation
            slot = self.conv_nodes[driver.job.tag]
            if failed is not None or self.aborted:
                outputs['conv_before_silu_partial'] = bytes(slot['data'])
                outputs['conv_before_silu_seen'] = bytes(slot['seen'])
        if failed is None and not self.aborted:
            outputs[self.role] = driver.output.raw()
            self.producer_hashes[driver.output.base] = sha(outputs[self.role])
            if self.role == 'conv_silu':
                outputs['conv_before_silu'] = bytes(self.conv_nodes[driver.job.tag]['data'])
                outputs['history_staging'] = driver.history_out.raw()
                self.producer_hashes[driver.history_out.base] = sha(outputs['history_staging'])
            if self.role == 'chunk':
                outputs['state_staging'] = driver.state_out.raw()
                self.producer_hashes[driver.state_out.base] = sha(outputs['state_staging'])
        report.update(phase=self.phase, role=self.role, owner_tag=driver.job.tag,
                      terminal_status=failed, terminal_accepted=True, complete=True, status=failed,
                      block_generation=self.roots.generation,
                      block_committed=self.response is not None and self.response.status is None)
        self.commands.append(report)
        completed_role = self.role
        self.active = None
        self._index += 1
        if self.observe is not None:
            self.observe(self.phase, completed_role, report, outputs)
        self._check_resources()
        return event

    def reset(self):
        """Reset drained poisoned owners in place; preserve committed roots.

        Existing partial staging is never made fresh or reused. A subsequent
        start must select an unused preallocated input window.
        """
        require(self.response is not None and self.active is None and self.memory.pending is None and
                self.matrix.owner is None and self.scalar.client is None and self.vector.client is None,
                'reset cannot erase an accepted request or held block terminal')
        self.matrix.reset()
        self.dense.tick(coordinated_reset=True)
        for owner in (self.rms, self.conv, self.prep, self.chunk, self.norm, self.elementwise):
            owner.reset()
        self.locked = self.aborted = False
        self._check_resources()

    def _progress_snapshot(self, elapsed_seconds):
        owner = None if self.active is None else self.active.owner
        context = self.chunk.context if self.role == 'chunk' and owner is not None else {}
        require(type(context) is dict, 'progress requires plain chunk context')
        snapshot = FullBlockProgress(self.phase, self.role, self.ticks,
            getattr(owner, 'state', None), getattr(owner, 'ticks', None),
            context.get('phase'), context.get('head'), context.get('chunk'),
            self.roots.generation, len(self.commands), float(elapsed_seconds))
        # Do not coerce arbitrary model objects via str/int or leak them through
        # annotations alone. Reject subclasses as well as mutable field values.
        expected = (str, str, int, str, int, str, int, int, int, int, float)
        optional = (3, 4, 5, 6, 7)
        require(all(type(value) is kind or (index in optional and value is None)
                    for index, (value, kind) in enumerate(zip(snapshot, expected))),
                'progress fields must be detached exact primitives')
        return snapshot

    def run_window(self, phase, *, cold, expected_generation, budget_seconds=1800, hook=None,
                   progress=None, progress_interval_seconds=30):
        """Run unchanged transport with optional rate-limited read-only telemetry.

        Unlike legacy hook(self), progress receives no live objects and cannot
        supply controls. This is a trusted diagnostic API, not a Python sandbox.
        It runs before tick's existing resource guard, never inside final
        preflight/acceptance/joint commit. Exceptions propagate to
        run's owned FAILED summary; no synthetic owner receipt is manufactured.
        No terminal notification is forced: observe remains the terminal API.
        """
        require(type(budget_seconds) in (int, float) and 0 < budget_seconds <= 7200,
                'bounded positive wall budget required')
        if progress is not None:
            require(callable(progress) and type(progress_interval_seconds) in (int, float) and
                    1 <= progress_interval_seconds <= 7200,
                    'progress requires callable and 1..7200 second cadence')
        self.start(phase, cold=cold, expected_generation=expected_generation)
        started = time.monotonic()
        deadline, drain_deadline = started + budget_seconds, None
        next_progress = started
        while self.response is None:
            now = time.monotonic()
            if now >= deadline and drain_deadline is None:
                drain_deadline = now + 60
            require(drain_deadline is None or now < drain_deadline, 'abort drain exceeded wall budget')
            controls = {} if hook is None else dict(hook(self) or {})
            if drain_deadline is not None:
                controls = {'abort': True}
            if progress is not None and now >= next_progress:
                progress(self._progress_snapshot(now - started))
                next_progress = now + progress_interval_seconds
            self.tick(**controls)
        return self.response

    def report(self):
        self._check_resources()
        return dict(scope=SCOPE, arithmetic_seal_schema=FULL_ARITHMETIC_SEAL_SCHEMA,
                    public_command128_executed=False, rtl_executed=False,
                    hardware_cycles=None, hardware_mac_utilization=None, native_acceptance=False,
                    rms_policy=self.policy.value, vector_policy=self.vector.exception_policy,
                    projection_policy=self.projection_policy.value,
                    projection_profile=None if self.projection_profile is None else asdict(self.projection_profile),
                    vector_fatal_mask=self.vector.fatal_mask,
                    vector_arithmetic_backend=self.vector.backend_report(),
                    scalar_arithmetic_binding=self._scalar_guard.report(self.scalar),
                    chunk_exp_policy=self.chunk_exp_policy,
                    chunk_exp_identity=chunk.ep.identity(self.chunk_exp_policy),
                    chunk_cumsum_policy=self.chunk.cumsum_policy, chunk_matmul_policy=self.chunk.matmul_policy,
                    vector_policy_control_bound_to_current_chisel=False,
                    roots=asdict(self.roots), response=None if self.response is None else asdict(self.response),
                    reset_required=self.locked, commands=self.commands, window_inputs=self.window_inputs,
                    full_block_executed=self.roots.generation > 0,
                    source_initialization='raw_inputs_and_parameters_only_before_launch',
                    carried_dependency='preceding_actual_committed_history_and_fp32_state',
                    software_ticks=self.ticks,
                    conv_observations={tag: self._conv_observation(tag) for tag in self.conv_nodes})


def freeze_identity(root, fixture, weights, inputs, library, vector, output,
                    projection_policy=ProjectionPolicy.Legacy, *, scalar=None,
                    chunk_exp_policy=chunk.ep.LEGACY_EXP):
    """Snapshot only execution/validation sources, not numerical references."""
    from .input_fixture import SOURCE_FILES
    require(type(vector) is Vector16, 'original Vector16 required for execution snapshot')
    vector.arithmetic_identity()
    require(verify_library(vector.library, arithmetic_backend=vector.backend_identity.backend)[2] ==
            vector.backend_identity, 'Vector native build changed after construction')
    scalar_binding = _admit_chunk_scalar(chunk_exp_policy, vector, scalar).report(scalar)
    exp_identity = chunk.ep.identity(chunk_exp_policy)
    matrix_receipt = Path(os.environ['MATRIX_SERVICE_COMPILE_RECEIPT']).resolve(strict=True)
    vector_receipt = vector.library.with_suffix('.json')
    build = json.loads(matrix_receipt.read_text())
    compiled = build.get('source_sha256', build.get('sources_before'))
    require(type(compiled) is dict and compiled, 'verified Matrix compile source closure required')
    extra_sources = ()
    if ProjectionPolicy(projection_policy) is ProjectionPolicy.IndependentK512:
        from .projection_driver import SOURCE_FILES as PROJECTION_SOURCES
        extra_sources = PROJECTION_SOURCES
    names = sorted(set(ACTUAL_SOURCE_FILES) | set(SOURCE_FILES) | set(compiled) | set(extra_sources) |
                   {vector.backend_identity.source})
    sources = {}
    for name in names:
        raw = (root / name).read_bytes()
        sources[name] = sha(raw)
        target = output / 'source_snapshot' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    compiler = build['compiler']['path'] if type(build['compiler']) is dict else build['compiler']
    vector_build = json.loads(vector_receipt.read_text())
    files = (Path(library), matrix_receipt, vector.library, vector_receipt,
             Path(fixture) / 'manifest.json', Path(compiler), Path(vector_build['argv'][0]))
    receipts = output / 'compiled_receipts'
    receipts.mkdir()
    (receipts / 'matrix.json').write_bytes(matrix_receipt.read_bytes())
    (receipts / 'vector.json').write_bytes(vector_receipt.read_bytes())
    return dict(scope=SCOPE, arithmetic_seal_schema=FULL_ARITHMETIC_SEAL_SCHEMA, source_sha256=sources,
                source_scope='actual_software_execution_and_input_build_validation_only',
                identity_file_sha256={str(path.resolve()): sha(path.read_bytes()) for path in files},
                parameter_sha256={name: sha(raw) for name, raw in weights.items()},
                authenticated_input_sha256={name: sha(raw) for name, raw in inputs.items()},
                library=str(library), compile_receipt=str(matrix_receipt), matrix_compiler=str(Path(compiler).resolve()),
                vector_library=str(vector.library), vector_compile_receipt=str(vector_receipt),
                vector_compiler=str(Path(vector_build['argv'][0]).resolve()),
                fixture_manifest=str((Path(fixture) / 'manifest.json').resolve()),
                vector_exception_policy=vector.exception_policy, vector_fatal_mask=vector.fatal_mask,
                vector_arithmetic_backend=vector.backend_report(),
                scalar_arithmetic_binding=scalar_binding, chunk_exp_policy=chunk_exp_policy,
                chunk_exp_identity=exp_identity, chunk_cumsum_policy=chunk.LEGACY_CUMSUM,
                chunk_matmul_policy=chunk.LEGACY_MATMUL,
                public_command128_executed=False, rtl_executed=False)


def final_identity(identity, root, fixture):
    """Missing or changed sources retain a failure receipt even on exceptions."""
    from .input_fixture import load_fixture, gdn
    checks, errors = {}, {}
    def check(name, probe):
        try:
            checks[name] = bool(probe())
        except (OSError, ValueError, KeyError) as error:
            checks[name] = False
            errors[name] = {'type': type(error).__name__, 'message': str(error)}
    check('source_unchanged', lambda: identity['source_sha256'] == {
        name: sha((root / name).read_bytes()) for name in identity['source_sha256']})
    check('libraries_receipts_fixture_unchanged', lambda: all(
        sha(Path(path).read_bytes()) == digest for path, digest in identity['identity_file_sha256'].items()))
    def inputs_unchanged():
        manifest, inputs = load_fixture(root, fixture)
        _, weights = gdn.load_payload(root, Path(manifest['sources']['layer0_directory']))
        return (identity['parameter_sha256'] == {name: sha(raw) for name, raw in weights.items()} and
                identity['authenticated_input_sha256'] == {name: sha(raw) for name, raw in inputs.items()})
    check('authenticated_inputs_unchanged', inputs_unchanged)
    def same_files(keys):
        return all(sha(Path(identity[key]).read_bytes()) ==
                   identity['identity_file_sha256'][str(Path(identity[key]).resolve())] for key in keys)
    check('library_unchanged', lambda: same_files(('library', 'compile_receipt', 'matrix_compiler')))
    check('vector_library_unchanged', lambda: same_files(('vector_library', 'vector_compile_receipt', 'vector_compiler')))
    check('fixture_unchanged', lambda: same_files(('fixture_manifest',)) and checks['authenticated_inputs_unchanged'])
    return dict(**checks, identity_read_errors=errors)


def run(fixture, output, *, rows=16, budget_seconds=1800, vector=None, vector_library=None,
        rms_policy=rms.ReductionPolicy.Torch210CpuDefault1024, observe=None,
        vector_exception_policy=LEGACY_POLICY, projection_policy=ProjectionPolicy.Legacy,
        vector_arithmetic_backend=LEGACY_BACKEND, chunk_exp_policy=chunk.ep.LEGACY_EXP,
        progress=None, progress_interval_seconds=30, window_budget_seconds=None):
    """Actual-only two-window entrypoint. Existing libraries only; never builds.

    progress receives bounded-cadence FullBlockProgress snapshots, not outputs
    or live resources. elapsed_seconds restarts for each window. It cannot
    select controls; legacy terminal observe behavior is unchanged. An explicit
    window_budget_seconds caps each window at min(remaining total, cap) without
    changing run_window's 7200 second ceiling. None preserves legacy behavior.
    """
    from .input_fixture import ROOT, load_fixture, gdn
    from ..qwen2_resident_matrix.ffn_attention.matrix_service import configure_library
    require(type(rows) is int and rows in (16, 128), 'M16 or M128 only')
    if window_budget_seconds is not None:
        require(type(window_budget_seconds) in (int, float) and 0 < window_budget_seconds <= 7200,
                'bounded positive per-window wall budget required')
    output = Path(output)
    require(not output.exists(), 'fresh output directory required')
    require((vector is None) != (vector_library is None), 'explicit Vector16 or existing Vector16 library required')
    output.mkdir(parents=True)
    start, coordinator, identity = time.monotonic(), None, None
    output_files = {}
    def persist(name, value):
        (output / name).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')
    def record(phase, role, report, actual):
        for name, raw in actual.items():
            dtype = ('u8' if name == 'conv_before_silu_seen' else
                     'fp32le' if name in ('prep', 'state_staging') else 'bf16le')
            filename = f'{phase}.{name}.actual.{dtype}'
            (output / filename).write_bytes(raw)
            output_files[filename] = dict(bytes=len(raw), sha256=sha(raw))
        persist('progress.json', coordinator.report())
        if observe is not None:
            observe(phase, role, report, actual)
    persist('summary.json', dict(scope=SCOPE, status='RUNNING', rows=rows,
                                public_command128_executed=False, rtl_executed=False))
    try:
        manifest, inputs = load_fixture(ROOT, fixture)
        _, weights = gdn.load_payload(ROOT, Path(manifest['sources']['layer0_directory']))
        library = d.library_from_environment(ROOT)
        if vector is None:
            vector = Vector16(vector_library, exception_policy=vector_exception_policy,
                              arithmetic_backend=vector_arithmetic_backend)
        scalar = _new_chunk_scalar(chunk_exp_policy, vector)
        identity = freeze_identity(ROOT, fixture, weights, inputs, library, vector, output,
                                   projection_policy, scalar=scalar, chunk_exp_policy=chunk_exp_policy)
        selected_projection = ProjectionPolicy(projection_policy)
        if selected_projection is ProjectionPolicy.IndependentK512:
            from .projection_driver import GDN_PROJECTION_PROFILE
            projection_profile = asdict(GDN_PROJECTION_PROFILE)
        else:
            projection_profile = None
        identity.update(rows=rows, projection_policy=selected_projection.value,
                        projection_profile=projection_profile, rms_policy=rms.ReductionPolicy(rms_policy).value,
                        input_sha256={phase: sha(inputs[phase + '.hidden.bf16le'][:rows * 2048])
                                      for phase in ('cold128', 'carried128')},
                        token_fixture_slices={'cold128': [0, rows], 'carried128': [128, 128 + rows]})
        persist('identity.json', identity)
        lib = configure_library(C.CDLL(str(library)))
        require(lib.td_reset() == 0, 'one initial Matrix reset required')
        matrix = d.MatrixService(lib)
        coordinator = FullBlockCoordinator(weights,
            {phase: inputs[phase + '.hidden.bf16le'][:rows * 2048] for phase in ('cold128', 'carried128')},
            matrix=matrix, vector=vector, scalar=scalar, rms_policy=rms_policy,
            projection_policy=projection_policy, observe=record, chunk_exp_policy=chunk_exp_policy)
        for phase, cold in (('cold128', True), ('carried128', False)):
            remaining = budget_seconds - (time.monotonic() - start)
            require(remaining > 0, 'full coordinator wall budget exceeded')
            result = coordinator.run_window(phase, cold=cold, expected_generation=coordinator.roots.generation,
                                            budget_seconds=(remaining if window_budget_seconds is None else
                                                            min(remaining, window_budget_seconds)),
                                            progress=progress,
                                            progress_interval_seconds=progress_interval_seconds)
            if result.status is not None:
                break
        report = coordinator.report()
        verification = final_identity(identity, ROOT, fixture)
        verification['scalar_arithmetic_binding_unchanged'] = (
            report['scalar_arithmetic_binding'] == identity['scalar_arithmetic_binding'])
        verification['chunk_exp_binding_unchanged'] = all(report[name] == identity[name] for name in
            ('arithmetic_seal_schema', 'chunk_exp_policy', 'chunk_exp_identity',
             'chunk_cumsum_policy', 'chunk_matmul_policy'))
        verification['output_files_unchanged'] = all((output / name).stat().st_size == item['bytes'] and
            sha((output / name).read_bytes()) == item['sha256'] for name, item in output_files.items())
        complete = coordinator.roots.generation == 2 and all(
            value for name, value in verification.items() if name != 'identity_read_errors')
        report.update(**{name: verification[name] for name in ('source_unchanged', 'fixture_unchanged',
                                                               'library_unchanged', 'vector_library_unchanged')})
        report.update(identity=identity, output_files=output_files, terminal_count=len(coordinator.commands),
                      final_identity=verification, elapsed_seconds=time.monotonic() - start,
                      status='ACTUAL_COMPLETE_UNCOMPARED' if complete else 'FAILED')
        if complete:
            persist('actual_terminal.json', report)
        persist('summary.json', report)
        return report
    except BaseException as error:
        try:
            report = dict(scope=SCOPE) if coordinator is None else coordinator.report()
        except Exception as report_error:
            # An invalid final callback/resource must retain FAILED evidence,
            # not suppress the summary or issue an unverified success report.
            report = dict(scope=SCOPE, full_block_executed=False, native_acceptance=False,
                public_command128_executed=False, rtl_executed=False,
                live_resource_identity_valid=False,
                report_error={'type': type(report_error).__name__, 'message': str(report_error)})
        report.update(identity=identity, output_files=output_files, status='FAILED', elapsed_seconds=time.monotonic() - start,
                      error={'type': type(error).__name__, 'message': str(error)})
        if identity is not None:
            report['final_identity'] = final_identity(identity, ROOT, fixture)
        persist('summary.json', report)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--vector-library', required=True)
    parser.add_argument('--vector-exception-policy', choices=(LEGACY_POLICY, IEEE_POLICY), default=LEGACY_POLICY)
    parser.add_argument('--vector-arithmetic-backend', choices=ARITHMETIC_BACKENDS, default=LEGACY_BACKEND)
    parser.add_argument('--projection-policy', choices=tuple(p.value for p in ProjectionPolicy),
                        default=ProjectionPolicy.Legacy.value)
    parser.add_argument('--chunk-exp-policy',
                        choices=(chunk.ep.LEGACY_EXP, chunk.ep.EQUAL_HEADS_EXPERIMENTAL_EXP),
                        default=chunk.ep.LEGACY_EXP)
    parser.add_argument('--rows', type=int, choices=(16, 128), default=16)
    parser.add_argument('--budget-seconds', type=int, default=1800)
    args = parser.parse_args()
    result = run(args.fixture, args.output, rows=args.rows, budget_seconds=args.budget_seconds,
                 vector_library=args.vector_library, vector_exception_policy=args.vector_exception_policy,
                 vector_arithmetic_backend=args.vector_arithmetic_backend,
                 projection_policy=args.projection_policy, chunk_exp_policy=args.chunk_exp_policy)
    print(json.dumps({'status': result['status'], 'roots': result['roots']}), flush=True)
    return 0 if result['status'] == 'ACTUAL_COMPLETE_UNCOMPARED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
