"""Validated importer for local Attention/SiLU/E3 service-curve JSON."""
from __future__ import annotations
from dataclasses import dataclass,asdict
import hashlib,json,math
from pathlib import Path
from typing import Mapping

REQUIRED=("attention_matrix_cycles","attention_sfu_cycles","silu_cycles","matrix_producer_stall_cycles","matrix_queue_bubble_cycles","sram_bank_conflict_cycles","event_wait_signal_cycles","ddr_read_bytes","ddr_write_bytes","ddr_read_efficiency","ddr_write_efficiency","score_ddr_bytes","probability_ddr_bytes")

@dataclass(frozen=True)
class Curve:
    commit:str;source_sha256:str;sequence:int;clock_hz:int;attention_matrix_cycles:int;attention_sfu_cycles:int;silu_cycles:int;matrix_producer_stall_cycles:int;matrix_queue_bubble_cycles:int;sram_bank_conflict_cycles:int;event_wait_signal_cycles:int;ddr_read_bytes:int;ddr_write_bytes:int;ddr_read_efficiency:float;ddr_write_efficiency:float;score_ddr_bytes:int;probability_ddr_bytes:int;evidence_class:str


def parse(raw:Mapping[str,object])->Curve:
    missing=[k for k in ("commit","source_sha256","sequence","clock_hz","evidence_class",*REQUIRED) if k not in raw]
    if missing: raise ValueError(f"missing:{missing}")
    c=Curve(
        commit=str(raw["commit"]), source_sha256=str(raw["source_sha256"]),
        sequence=int(raw["sequence"]), clock_hz=int(raw["clock_hz"]),
        attention_matrix_cycles=int(raw["attention_matrix_cycles"]),
        attention_sfu_cycles=int(raw["attention_sfu_cycles"]),
        silu_cycles=int(raw["silu_cycles"]),
        matrix_producer_stall_cycles=int(raw["matrix_producer_stall_cycles"]),
        matrix_queue_bubble_cycles=int(raw["matrix_queue_bubble_cycles"]),
        sram_bank_conflict_cycles=int(raw["sram_bank_conflict_cycles"]),
        event_wait_signal_cycles=int(raw["event_wait_signal_cycles"]),
        ddr_read_bytes=int(raw["ddr_read_bytes"]), ddr_write_bytes=int(raw["ddr_write_bytes"]),
        ddr_read_efficiency=float(raw["ddr_read_efficiency"]), ddr_write_efficiency=float(raw["ddr_write_efficiency"]),
        score_ddr_bytes=int(raw["score_ddr_bytes"]), probability_ddr_bytes=int(raw["probability_ddr_bytes"]),
        evidence_class=str(raw["evidence_class"]),
    )
    if len(c.commit)<7 or len(c.source_sha256)!=64: raise ValueError("identity")
    if c.sequence not in (128,384,1024) or c.clock_hz!=1_000_000_000: raise ValueError("shape/clock")
    numeric=[c.attention_matrix_cycles,c.attention_sfu_cycles,c.silu_cycles,c.matrix_producer_stall_cycles,c.matrix_queue_bubble_cycles,c.sram_bank_conflict_cycles,c.event_wait_signal_cycles,c.ddr_read_bytes,c.ddr_write_bytes,c.score_ddr_bytes,c.probability_ddr_bytes]
    if any(v<0 for v in numeric): raise ValueError("negative")
    if not 0<c.ddr_read_efficiency<=1 or not 0<c.ddr_write_efficiency<=1: raise ValueError("efficiency")
    if c.evidence_class not in {"E1_MEASURED","E2_INTEGRATED","E3_INTEGRATED"}: raise ValueError("evidence")
    return c


def calibrate(curve:Curve)->dict[str,object]:
    # Frozen q1024 one-block constants from the v6.9 analytical model.
    matrix_other=93_585_432;sfu_other=507_932;write_peak=40.0;read_peak=100.0;baseline=1_311;layers=28
    matrix=matrix_other+curve.attention_matrix_cycles+curve.matrix_producer_stall_cycles+curve.matrix_queue_bubble_cycles
    sfu=sfu_other+curve.attention_sfu_cycles+curve.silu_cycles
    compute=matrix+sfu+curve.sram_bank_conflict_cycles+curve.event_wait_signal_cycles
    read=math.ceil(curve.ddr_read_bytes/(read_peak*curve.ddr_read_efficiency));write=math.ceil(curve.ddr_write_bytes/(write_peak*curve.ddr_write_efficiency))
    spill=max(0,read-math.floor(compute*0.15));block=compute+spill+write+baseline;full=block*layers;tps=curve.sequence*curve.clock_hz/full
    lane="one" if curve.matrix_producer_stall_cycles/max(matrix,1)<=0.02 else "two"
    return {"block_cycles":block,"full_model_cycles":full,"tokens_per_second":tps,"review_floor_pass":tps>=315,"target_pass":tps>=300,"selected_silu_lanes":lane,"producer_stall_fraction":curve.matrix_producer_stall_cycles/max(matrix,1),"score_probability_ddr_zero":curve.score_ddr_bytes==0 and curve.probability_ddr_bytes==0,"sram_ddr_counters_present":True}


def import_report(raw:Mapping[str,object])->dict[str,object]:
    curve=parse(raw);cal=calibrate(curve);digest=hashlib.sha256(json.dumps({"curve":asdict(curve),"calibration":cal},sort_keys=True,separators=(",",":")).encode()).hexdigest()
    status="PASS_REVIEW" if cal["review_floor_pass"] and cal["score_probability_ddr_zero"] else ("PASS_TARGET_ONLY_REOPEN_MARGIN" if cal["target_pass"] else "FAIL_REOPEN_ARCHITECTURE")
    return {"schema_version":1,"status":status,"curve":asdict(curve),"calibration":cal,"sha256":digest,"stop_rule":"Below 315 tps or nonzero score/probability DDR bytes reopens the architecture/performance budget."}


def load(path:str|Path)->dict[str,object]:return import_report(json.loads(Path(path).read_text()))

def sample_curve(*,degraded:bool=False)->dict[str,object]:
    return {"commit":"deadbee123456789","source_sha256":"1"*64,"sequence":1024,"clock_hz":1_000_000_000,"attention_matrix_cycles":3_244_166 if not degraded else 4_500_000,"attention_sfu_cycles":1_579_008 if not degraded else 2_500_000,"silu_cycles":9_175_040 if not degraded else 14_000_000,"matrix_producer_stall_cycles":500_000 if not degraded else 8_000_000,"matrix_queue_bubble_cycles":600_000 if not degraded else 8_000_000,"sram_bank_conflict_cycles":300_000 if not degraded else 6_000_000,"event_wait_signal_cycles":1_000 if not degraded else 100_000,"ddr_read_bytes":93_585_408,"ddr_write_bytes":1_048_576,"ddr_read_efficiency":0.8 if not degraded else 0.4,"ddr_write_efficiency":0.8 if not degraded else 0.4,"score_ddr_bytes":0,"probability_ddr_bytes":0,"evidence_class":"E3_INTEGRATED"}
