"""Static, optimistic bounds for a K16 / all-M128 on-chip Dense schedule.

No off-chip partial sums, no reordering within an output's increasing-K
sequence, no change to the original external storage or physical 4096 MACs.
This is neither a simulator nor a claim that the bank/port schedule exists.
"""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path

PINNED = {
    "pc1": "2708229e7e3f3f23998ad465f731b369a39f04173128055e866e3ab5b4ff1975",
    "qwen2": "fc4b3afa41eb01fb1186354ae28917acea49fc69d3c26cd97e4e1b715426b643",
}
M, N_TILE, K_TILE, MACS = 128, 256, 16, 4096
A_BYTES = 704512
W_BYTES = 81920
BASE_ACC = 5 * 16 * N_TILE * 4
A_LOGICAL_READ_PORT_BYTES_PER_CYCLE = 16 * 32
RX_PANEL_BYTES = 2 * M * K_TILE * 2
TARGETS = (80, 90)

def ceildiv(a, b):
    return -(-a // b)

def require(p, msg):
    if not p:
        raise ValueError(msg)

def verified(path, digest):
    b = Path(path).read_bytes()
    require(hashlib.sha256(b).hexdigest() == digest, f"input pin mismatch: {path}")
    return json.loads(b)

def evaluate(n, k, width, n_tiles_per_group):
    require(n % N_TILE == 0 and k > 0 and k % K_TILE == 0 and width in (2,4),
            "unqualified geometry or external datatype")
    n_tiles = n // N_TILE
    require(1 <= n_tiles_per_group <= n_tiles, "invalid concurrent N extent")
    groups = ceildiv(n_tiles, n_tiles_per_group)
    # Allocate local BF16 A at M16 granularity; reserve ping-pong full M K16
    # panels first. Uncached rows cost a reread for each N group. DDR input
    # format remains FP32/BF16, notwithstanding existing ingress BF16 packing.
    full_a = M * k * 2
    cached_rows = min(M, (A_BYTES-RX_PANEL_BYTES)//(16*k*2)*16)
    a_ext = (cached_rows+groups*(M-cached_rows))*k*width
    w_ext = n*k*width
    acc = M*N_TILE*n_tiles_per_group*4
    useful = M*n*k
    lower = {}
    for bw in (64,100):
        floor = max(ceildiv(useful,MACS),ceildiv(a_ext+w_ext,bw))
        lower[str(bw)] = {
            "min_cycles":floor,
            "dense_only_utilization_upper":str(Fraction(useful,MACS*floor)),
            "read_deficit_B_at_90_pct":max(0,a_ext+w_ext-bw*(useful*10//(MACS*9))),
        }
    return {
        "n_tiles_per_group": n_tiles_per_group,
        "serial_n_groups":groups,
        "cached_m_rows":cached_rows,
        "a_local_bytes":cached_rows*k*2,
        "a_full_local_bytes":full_a,
        "a_panel_reservation_bytes":RX_PANEL_BYTES,
        "a_external_bytes":a_ext,
        "unique_weight_bytes":w_ext,
        "required_weight_read_passes":1,
        "accumulator_logical_bytes":acc,
        "extra_logical_accumulator_bytes_vs_original":acc-BASE_ACC,
        "output_bytes_omitted_from_read_envelope":M*n*width,
        "both_reads_optimistically_overlapped_with_compute":lower,
        "weight_only_bytes_per_cycle_required":{str(t):str(Fraction(w_ext*MACS*t,useful*100)) for t in TARGETS},
        "read_bytes_per_cycle_required":{str(t):str(Fraction((w_ext+a_ext)*MACS*t,useful*100)) for t in TARGETS},
    }

def pareto(rows):
    return [p for p in rows if not any(q["accumulator_logical_bytes"] < p["accumulator_logical_bytes"]
        and q["a_external_bytes"] <= p["a_external_bytes"] for q in rows)]

def study(pc1, qwen2):
    require(pc1["physical_mac_slots_per_cycle"]==4096 and pc1["hardware_executed"] is False
        and [x["profile"] for x in pc1["rows"]]==list(range(5)), "wrong first-projection input")
    require(qwen2["hardware_executed"] is False and [p["pc"] for p in qwen2["dense"]]==[1,4,7,13,16,17,19],
        "wrong pinned Qwen2 dense recipe")
    def scenarios(m,n,k,w):
        require(m==128,"not M128")
        return pareto([evaluate(n,k,w,j) for j in range(1,n//N_TILE+1)])
    p1 = [{"profile":p["profile"], "scenarios":scenarios(p["m"],p["n"],p["k"],4 if p["input_storage"]=="FP32" else 2)}
        for p in pc1["rows"]]
    q = [{"pc":p["pc"], "role":p["role"], "shape":p["shape"], "scenarios":scenarios(*p["shape"],4)}
        for p in qwen2["dense"]]
    require(q[0]["scenarios"]==p1[0]["scenarios"],"independent shape disagreement")
    # One read of one K16 N256 weight block is saved by fixing the original
    # 80+48 split. There are three extra M16 accumulator blocks to spill.
    spill = {"extra_context_readback_bytes_per_K16":3*16*N_TILE*4,
             "extra_context_write_bytes_per_K16":3*16*N_TILE*4,
             "one_weight_tile_saved_FP32_bytes":K_TILE*N_TILE*4,
             "one_weight_tile_saved_BF16_bytes":K_TILE*N_TILE*2}
    # Best conceivable traffic if one bank holds off-array spilled C. At
    # 90% target a 128-row K16xN256 group must average <= 128/0.9 cycles.
    # No claim about latency or ability to re-seed on the original interface.
    group_ideal_cycles = M*K_TILE*N_TILE//MACS
    spill["minimum_bidirectional_bytes_per_cycle_at_90_pct"] = str(
        Fraction((spill["extra_context_readback_bytes_per_K16"]+spill["extra_context_write_bytes_per_K16"])*9,
                 group_ideal_cycles*10))
    spill["minimum_each_direction_bytes_per_cycle_at_90_pct"] = str(
        Fraction(spill["extra_context_readback_bytes_per_K16"]*9, group_ideal_cycles*10))
    return {"schema":"hetero_m128_optimistic_onchip_reuse_v1","scope":"STATIC NOT IMPLEMENTED",
        "physical_Matrix_MACs":MACS,"original_A_bank_bytes":A_BYTES,"original_weight_banks_bytes":W_BYTES,
        "original_A_bank_port_width_sum_B_per_cycle_one_direction":A_LOGICAL_READ_PORT_BYTES_PER_CYCLE,
        "different_read_and_write_port_concurrency_not_assumed":True,
        "original_logical_accumulator_bytes":BASE_ACC,"fixed_external_read_B_per_cycle":64,
        "hypothetical_not_measured_read_B_per_cycle":100,"no_write_or_control_timing_included":True,
        "bank_conflicts_and_port_count_not_proven":True,"whole_block_utilization":None,
        "starting_accumulator_candidate":"No off-chip spill; K16 visited in order per output; one K16 weight tile fanout across all 8 groups of M16",
        "full_group_spill_80plus48_negative_example":spill,"pc1":p1,"qwen2_dense":q,"pinned_input_results":PINNED}

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--pc1",required=True)
    ap.add_argument("--qwen2",required=True)
    arg=ap.parse_args()
    print(json.dumps(study(verified(arg.pc1,PINNED["pc1"]),verified(arg.qwen2,PINNED["qwen2"])),
                     indent=2,sort_keys=True))
