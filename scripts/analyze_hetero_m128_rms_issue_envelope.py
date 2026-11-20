"""Source-specific BF16 RMS PC0 design study; no DUT emulation or cycle benchmark."""
import hashlib
import json
import sys
from pathlib import Path

def require(condition, msg):
    if not condition:
        raise ValueError(msg)

def ceildiv(x, y):
    return (x + y - 1) // y

def resident(width, rows=128):
    require(width in (1024, 2048) and rows == 128, 'not an audited RMS geometry')
    rb = width * 2
    # Conservative sizing: preserve the full existing output/FP32 residue bank
    # and its wrapping; cache full input row and gamma independently.
    return dict(width=width, rows=rows, original_three_banks_bytes=6144,
                full_row_single_slot_data_bytes=rb,
                full_gamma_data_bytes=rb,
                output_and_partial_bank_data_bytes=2048,
                resident_bytes=2*rb+2048, additional_data_bytes=2*rb+2048-6144,
                original_axi_bytes=dict(reduce_input=rb*rows, reread_input=rb*rows,
                                        reread_gamma=rb*rows, output=rb*rows),
                resident_axi_bytes=dict(reduce_input=rb*rows, reread_input=0,
                                        gamma_initial_fill=rb, output=rb*rows))

def epilogue(width, lanes, interval, credit, release_latency):
    """Illustrative shared ALU/format issue scheduler, excluding all unmodelled work.

    Each request consumes one credit through retire. Three exact FP32 nodes exist
    per element group, then independent format; no FMA or intermediate BF16 cast.
    Order inside a shipped batch remains lane order. Gamma is independent.
    """
    require(width in (1024,2048) and (lanes, interval) in ((32,1),(64,2)), 'unreviewed width')
    require(credit > 0 and release_latency >= interval, 'invalid credit/latency')
    n = width // lanes
    deps = [(), (), (0,1), (2,)]
    ready = [[None]*4 for _ in range(n)]
    pending = []
    rows = []
    cycle, next_issue, peak = 0, 0, 0
    while len(rows) < n*4 or pending:
        for group, op, when in pending[:]:
            if cycle == when:
                ready[group][op] = cycle
                pending.remove((group,op,when))
        if cycle >= next_issue and len(pending) < credit:
            # Find earliest group on the wavefront, issuing only dependencies already retired.
            for group in range(n):
                elig = next((op for op in range(4)
                    if ready[group][op] is None and not any(x[:2] == (group,op) for x in pending)
                    and all(ready[group][d] is not None for d in deps[op])), None)
                if elig is not None:
                    pending.append((group,elig,cycle+release_latency))
                    rows.append((group,elig,cycle))
                    peak = max(peak,len(pending)); next_issue=cycle+interval
                    break
        cycle += 1
        require(cycle <= n*4*(release_latency+interval)+1, 'scheduler did not drain')
    return dict(lanes=lanes, interval=interval, latency_assumption_cycles=release_latency,
                credits=credit, saturation_credits_necessary=ceildiv(release_latency,interval),
                would_disable_steady_issue_for_credit=credit<ceildiv(release_latency,interval),
                children_per_request=lanes//32,
                simultaneous_packed_payload_min_bytes=credit*lanes*4,
                issues=len(rows), completion_boundary=cycle-1, high_watermark=peak,
                issue_payload_node_count=n*4*lanes)

def run(src):
    names = ('GdnRuntimeRmsNormOwnerV3.scala','BlockScalarFloatPolicyV2.scala',
             'UnifiedVectorElement32BankV4.scala','UnifiedVectorElement32ProtocolV4.scala')
    files = {n:(src/n).read_bytes() for n in names}
    signatures = {
      names[0]: ('val reduceIndex=Cat(lane(4),lane(3,0),lane(6,5),lane(9,7))',
                 'val input=Reg(Vec(32,UInt(512.W)))',
                 'is(root){operation:=inverse}', 'when(lane===1023.U)',
                 'val expectedMemory=(expectedFormat>>5)<<2', '5228.U,10412.U'),
      names[1]: ('new DivSqrtRecFN_small(8,24,0)', 'round_near_even',
                 'div.io.detectTininess:=tininess_afterRounding',
                 'io.request.ready:=state===idle'),
      names[2]: ('io.request.ready := !full || io.result.ready',),
      names[3]: ('val identity = new UnifiedSharedOperationTagV3','NOT wire-compatible')
    }
    for n, strings in signatures.items():
        require(all(s.encode() in files[n] for s in strings),f'unaudited source structure: {n}')
    return dict(layer='SOURCE_ARITHMETIC_AND_ILLUSTRATIVE_EPILOGUE_ONLY',
                files_sha256={n:hashlib.sha256(b).hexdigest() for n,b in files.items()},
                schedule=[epilogue(w,l,ii,c,6) for w in (1024,2048)
                          for l,ii in ((32,1),(64,2)) for c in (1,3,6)],
                capacity_and_traffic=[resident(w) for w in (1024,2048)],
                scalar_roots_per_128_rows=128, scalar_divides_per_128_rows=128,
                complete_mac_or_rtl_result=False,
                original_vec_bank_stall_coupled=True,
                constraints='Original FP32 reduction sequence and separate RNE sqrt/div preserved; illustrative epilogue excludes reduction, cache fill/write, stalls and exact SFU timing; no QoR or utilization claim.')

if __name__ == '__main__':
    print(json.dumps(run(Path(sys.argv[1])),indent=2,sort_keys=True))
