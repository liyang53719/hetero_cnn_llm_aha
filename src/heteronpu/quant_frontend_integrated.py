"""Integrated K-tail, block metadata, scale/tag FIFO reference model.

The model checks the source-ready RTL contract that connects the shared
K-tail sequencer to the existing GGML group decoder. It deliberately models
block request latency, two outstanding block slots, two decoded-beat slots and
random consumer backpressure. It is not RTL E1 evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import random

FORMATS = {"FP16": (16, 1), "Q8_0": (32, 2), "Q6_K": (256, 16), "Q3_K": (256, 16)}


@dataclass(frozen=True)
class Beat:
    fmt: str
    job_tag: int
    block: int
    group: int
    valid: int
    block_first: bool
    block_last: bool
    last: bool
    scale_tag: int
    subscale_tag: int


def expected_beats(fmt: str, k: int, job_tag: int) -> tuple[Beat, ...]:
    block_values, groups = FORMATS[fmt]
    if k < 0:
        raise ValueError("k")
    beats: list[Beat] = []
    remaining = k
    block = 0
    while remaining:
        in_block = min(remaining, block_values)
        group_count = math.ceil(in_block / 16)
        for group in range(group_count):
            valid = min(16, in_block - group * 16)
            beats.append(Beat(fmt, job_tag, block, group, valid, group == 0, group + 1 == group_count, remaining <= 16, (job_tag << 16) ^ block, (block << 4) ^ group))
            remaining -= valid
        block += 1
    return tuple(beats)


def simulate(fmt: str, k: int, *, job_tag: int, seed: int, block_slots: int = 2, beat_slots: int = 2) -> dict[str, object]:
    rng = random.Random(seed)
    expected = expected_beats(fmt, k, job_tag)
    total_blocks = 0 if not expected else expected[-1].block + 1
    requested = 0
    next_response_block = 0
    response_due: list[tuple[int, int]] = []
    payload_fifo: list[int] = []
    output_fifo: list[Beat] = []
    issued_index = 0
    retired: list[Beat] = []
    cycle = 0
    max_payload = max_output = 0
    request_stalls = output_stalls = 0
    while len(retired) < len(expected):
        # Issue block requests with random request-side backpressure.
        in_system = len(response_due) + len(payload_fifo)
        if requested < total_blocks and in_system < block_slots:
            if rng.random() >= 0.17:
                response_due.append((cycle + rng.randint(1, 9), requested))
                requested += 1
            else:
                request_stalls += 1
        # Responses are allowed to arrive only in request order, matching RTL contract.
        if response_due and response_due[0][0] <= cycle and len(payload_fifo) < block_slots:
            _, block = response_due.pop(0)
            if block != next_response_block:
                raise AssertionError((block, next_response_block))
            next_response_block += 1
            payload_fifo.append(block)
        # Decode one beat when the matching block payload exists and output FIFO has space.
        if issued_index < len(expected) and len(output_fifo) < beat_slots:
            beat = expected[issued_index]
            if payload_fifo and payload_fifo[0] == beat.block:
                output_fifo.append(beat)
                issued_index += 1
                if beat.block_last:
                    payload_fifo.pop(0)
        # Consumer backpressure.
        if output_fifo:
            if rng.random() >= 0.23:
                retired.append(output_fifo.pop(0))
            else:
                output_stalls += 1
        max_payload = max(max_payload, len(payload_fifo))
        max_output = max(max_output, len(output_fifo))
        cycle += 1
        if cycle > max(1000, len(expected) * 100):
            raise RuntimeError("frontend did not drain")
    if tuple(retired) != expected:
        raise AssertionError("tag/scale/beat mismatch")
    digest = hashlib.sha256(json.dumps([beat.__dict__ for beat in retired], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "format": fmt,
        "k": k,
        "beats": len(expected),
        "blocks": total_blocks,
        "cycles": cycle,
        "max_payload_fifo": max_payload,
        "max_output_fifo": max_output,
        "request_stall_cycles": request_stalls,
        "consumer_stall_cycles": output_stalls,
        "sha256": digest,
    }


def integrated_frontend_report(cases_per_format: int = 2000, seed: int = 0x7100) -> dict[str, object]:
    rng = random.Random(seed)
    records: list[dict[str, object]] = []
    directed = (0, 1, 15, 16, 17, 31, 32, 33, 255, 256, 257, 511, 512, 513, 1023, 1024, 1025, 4095, 4096, 4097)
    aggregate = hashlib.sha256()
    for fi, fmt in enumerate(FORMATS):
        ks = list(directed)
        ks.extend(rng.randrange(0, 16385) for _ in range(max(0, cases_per_format - len(ks))))
        for index, k in enumerate(ks):
            record = simulate(fmt, k, job_tag=(fi << 12) ^ index, seed=seed ^ fi * 0x101 ^ index)
            records.append(record)
            aggregate.update(bytes.fromhex(record["sha256"]))
    if any(record["max_payload_fifo"] > 2 or record["max_output_fifo"] > 2 for record in records):
        raise AssertionError("FIFO bound")
    return {
        "schema_version": 1,
        "status": "PASS",
        "evidence_class": "integrated_quant_frontend_E0_source_contract_not_RTL_E1",
        "formats": list(FORMATS),
        "cases": len(records),
        "cases_per_format": cases_per_format,
        "block_fifo_depth": 2,
        "beat_fifo_depth": 2,
        "tag_scale_alignment": "PASS",
        "response_order": "IN_ORDER_ASSERTED",
        "sha256": aggregate.hexdigest(),
        "remaining_local_gates": ["SystemVerilog elaboration", "Verilator E1", "shared dot-array integration", "pinned llama.cpp parity", "1GHz PPA"],
    }
