"""Fail-closed static PC1 useful-MAC contract. Does not run Chisel or compute utilization."""
import argparse
import hashlib
from fractions import Fraction
import json
from pathlib import Path

MACS = 4096
MAP_SHA = "0f5200a55824a430bd88c15ac5e571d045667613125c6376c2ba2485aebfbce7"
MAP_PATH = "round_20261119T1933/launch_pc2/FIVE_LAUNCH_MAP.json"
NAMES = ("Qwen2-1.5B", "Qwen3.5-0.8B L0", "Qwen3.5-0.8B L3",
         "Qwen3.5-35B-A3B L0", "Qwen3.5-35B-A3B L3")
END = 0xFFFFFF
SOURCE_PINS = {
    "StreamingDense.scala": "010fbea5d12e952e2083fa1f3f57cb1219f9756946b79dc01482e924c0c21bc5",
    "DenseReadPlanner.scala": "0f4c981b32170344c316e0b8dfe6296f2f497d4901365e05e0b9d730d1fd1886",
    "HostBlockTopV4.scala": "9c396be19ff3c6b70153ea7983a5f0e35b129445f0e7acadb3825e57191c2f86",
    "IdmaWeightBurst.scala": "935365723aba8d79675c84a1e23ce531741707d736d88e40ff2355eeda431ba4",
    "RetainedIdma.scala": "5d8873911046d0c4202e3f92ccfdc03c2ede3d8db06502473960ae3ed644f91e",
    "Qwen2Block.scala": "05248639be78683df68230ad1c4da3fe0449775d70e2fc7c3ff4aef0088567f9",
    "QwenOwnerProtocol.scala": "e63e70c168753a900664eec75283469d315317edb011d8c7ddd67636b165c159",
    "HostBlockCommandsV4.scala": "e25e8e87f1aa736f0a00b65b9cb839b967f6e907ad24a8a4014e22b0148a448c",
}
SOURCE_DIR = "round_20261119T1233/host/source"


def need(condition, reason):
    if not condition:
        raise ValueError(reason)

def bits(word, lo, width):
    return (word >> lo) & ((1 << width) - 1)

def pinned(root, name, sha, size=None):
    rel = Path(name)
    p = root / rel
    need(not rel.is_absolute() and '..' not in rel.parts and p.resolve() == p,
         "not an immutable workspace-relative path")
    data = p.read_bytes()
    need(size is None or len(data) == size, "pinned size")
    need(hashlib.sha256(data).hexdigest() == sha, "pinned SHA mismatch")
    return data

def ceildiv(a, b):
    return (a + b - 1) // b

def extract(profile, commands, descriptors):
    pid = profile['profile']
    launch = profile['launch']
    need(0 <= pid < len(NAMES) and launch['profileId'] == pid
         and profile['tokens'] == 128, "not the intended M128 profile")
    cc, dc = launch['commands'], launch['descriptors']
    need(cc >= 3 and dc > 0 and len(commands) == ceildiv(cc*16, 64)*64
         and len(descriptors) == ceildiv(dc*16, 64)*64, "table extent")
    need(not any(commands[cc*16:]) and not any(descriptors[dc*16:]), "nonzero table padding")

    def record(table, index, limit):
        need(0 <= index < limit, "descriptor index outside logical count")
        return int.from_bytes(table[16*index:16*(index+1)], "little")

    def desc(i, kind):
        d = record(descriptors, i, dc)
        need(bits(d, 0, 8) == kind and bits(d, 8, 24) == 0, f"descriptor kind {kind}")
        return d, bits(d, 32, 24)

    def tensor(root, write):
        base, shape_idx = desc(root, 1)
        shape, stride_idx = desc(shape_idx, 2)
        stride, tail = desc(stride_idx, 3)
        dtype = bits(base, 108, 4)
        need(dtype in (5,7) and bits(base, 116, 4) == 2
             and bits(base, 104, 4) == bits(base, 112, 4) == 0, "rank2 BF16/FP32")
        dims = tuple(bits(shape, 56+18*i, 18) for i in range(4))
        rows, cols = dims[:2]
        need(rows > 0 and cols > 0 and dims[2:] == (1,1)
             and tuple(bits(stride, 56+24*i, 24) for i in range(3)) == (cols,1,1), "contiguous shape")
        addr = bits(base,56,48) | (bits(base,120,8) << 48)
        count = rows * cols * (2 if dtype == 5 else 4)
        stop = addr + ceildiv(count,64)*64
        need(addr % 64 == 0 and any(x['base'] <= addr < stop <= x['limit'] and
             x['write' if write else 'read'] for x in launch['regions']), "tensor permission or bounds")
        return (rows, cols, dtype, addr, count, stop, tail)

    norm, proj, successor = (record(commands,i,cc) for i in range(3))
    need(bits(norm,0,8) in (0x30,0x32) and bits(proj,0,11) == 0x220 and
         bits(norm,40,16) != 0 and bits(norm,40,16) == bits(proj,24,16)
         and bits(proj,40,16) != 0 and bits(proj,40,16) == bits(successor,24,16),
         "PC1 order or event dependency")
    a,b,d = (tensor(bits(proj,56+24*i,24),i == 2) for i in range(3))
    nd = tensor(bits(norm,104,24), True)
    need(a[:6] == nd[:6] and all(d[3] >= x[5] or x[3] >= d[5] for x in (a,b)),
         "projection A does not alias exact PC0 D or output overlaps input")
    m,k = a[:2]
    n = b[1]
    need(m == 128 and b[0] == k and d[:2] == (m,n)
         and (a[2],b[2],d[2]) == ((7,7,7) if pid == 0 else (5,5,5))
         and b[6] == d[6] == END, "projection geometry/payload")
    policy, aux_idx = desc(a[6],0x10)
    aux, aux_tail = desc(aux_idx,0x12)
    need((bits(policy,56,16),bits(policy,72,16),bits(policy,88,24)) == (m,n,k)
         and bits(policy,112,16) == 0, "PC1 matrix policy shape or transpose")
    if pid == 0:
        need(aux_tail == END and bits(aux,56,72) == 0x4000040024FFFFFF, "Qwen2 auxiliary ABI")
    else:
        phase, extra_tail = desc(aux_tail, 0x21)
        need(extra_tail == END and bits(phase,56,72) == 0x1000203
             and bits(aux,56,72) == 0x004000040020FFFFFF, "BF16 cold role-0 typed auxiliary ABI")
    w = [s for s in profile['segments'] if s['address'] == b[3]]
    need(len(w) == 1 and w[0]['bytes'] == b[4] and w[0]['readonly'] is True,
         "PC1 has no complete original readonly weight segment")
    useful = m*n*k
    return dict(profile=pid, name=NAMES[pid], pc=1, m=m,n=n,k=k,
                input_storage="FP32" if pid == 0 else "BF16",
                expected_successful_pc1_useful_mac_delta=useful,
                exact_output_payload_bytes=d[4], weight_segment_sha256=w[0]['sha256'],
                a_base_alignment_mod_1k=a[3]%1024, weight_base_alignment_mod_1k=b[3]%1024,
                hard_lower_bound_matrix_cycles=ceildiv(useful,MACS),
                max_pc1_only_cycles_for_80_pct=(useful*5)//(MACS*4),
                max_pc1_only_cycles_for_90_pct=(useful*10)//(MACS*9))

def page_requests(base,stride,lanes,width):
    """Original owner read plans split by 1-KiB page and logical row/panel."""
    return sum(ceildiv((base+i*stride)%1024+width,1024) for i in range(lanes))

def streaming_envelope(m,n,k,a_word_bytes,b_word_bytes,a_base=0,b_base=0):
    """Single 64B R/cycle, ideal accepted beats; source-bound original Dense only."""
    need(m == 128 and n % 256 == 0 and k % 32 == 0 and max(a_word_bytes,b_word_bytes) <= 4,
         "out of original first-projection envelope")
    # DenseScratchGeometry uses 16*160*32 B for both W buffers. For K <=
    # 2048, 5 token tiles really fit; the architectural cap of 5 is active.
    weight_scratch = 16*160*32
    a_words_per_bank = min(5*(8960//16), (768*1024-weight_scratch)//(16*32))
    tiles = min(5, a_words_per_bank*16//k)
    need(tiles == 5, "first-projection capacity drift")
    cohorts = [min(16*tiles,m-i) for i in range(0,m,16*tiles)]
    useful = m*n*k
    # The source nContexts is exactly 1 for 5 or 3 M tiles. No whole-row
    # union of K requests is possible for these original N>=1536 profiles.
    a_plan_requests = page_requests(a_base,k*a_word_bytes,m,k*a_word_bytes)
    b_plan_requests = len(cohorts)*sum(
        page_requests(b_base+j*b_word_bytes,n*b_word_bytes,k,256*b_word_bytes)
        for j in range(0,n,256))
    a_beats = ceildiv(m*k*a_word_bytes,64)
    weights_per_cohort = ceildiv(k*n*b_word_bytes,64)
    # BF16 A needs two writes to the SAME 256-bit bank per R. The pending
    # upper-half write stalls R except that final per-cohort drain can overlap
    # setup; omit that one cycle and assume perfect no-bubble weight traffic.
    # A consumes an exclusive load phase before matrix execute in each cohort.
    min_a_cycles = a_beats if a_word_bytes == 4 else 2*a_beats-len(cohorts)
    ideal_floor = min_a_cycles + sum(max(ceildiv(c*n*k,MACS),weights_per_cohort) for c in cohorts)
    def q(n,d):
        return str(Fraction(n,d))
    return dict(
        original_m_cohorts=cohorts,
        fixed_a_bank_bytes=16*a_words_per_bank*32,
        fixed_weight_bank_bytes=weight_scratch,
        ideal_cached_A_bytes_for_128_rows_after_original_local_BF16_materialization=m*k*2,
        extra_logical_FP32_accumulator_payload_bytes_to_hold_eight_not_five_m16n256_contexts=(8-5)*16*256*4,
        weight_passes=len(cohorts),
        activation_response_beats=a_beats,
        activation_owner_burst_requests=a_plan_requests,
        weight_owner_burst_requests=b_plan_requests,
        weight_response_beats=weights_per_cohort*len(cohorts),
        mandatory_ideal_A_then_weight_epochs_cycle_floor=ideal_floor,
        ideal_pc1_fraction_upper_bound_excluding_all_write_and_command_cost=q(useful,MACS*ideal_floor),
        weight_only_fraction_upper_bound_64B_per_cycle=q(useful,MACS*weights_per_cohort*len(cohorts)),
        weight_only_fraction_upper_bound_hypothetical_100B_per_cycle=q(useful*100,MACS*64*weights_per_cohort*len(cohorts)),
        weight_only_bytes_per_cycle_needed_for_80_pct=q(MACS*64*weights_per_cohort*len(cohorts)*4,useful*5),
        weight_only_bytes_per_cycle_needed_for_90_pct=q(MACS*64*weights_per_cohort*len(cohorts)*9,useful*10),
        weight_only_reuse_all_128_once_fraction_upper_bound_64B_per_cycle=q(useful,MACS*max(weights_per_cohort,ceildiv(useful,MACS))),
        weight_only_reuse_all_128_once_fraction_upper_bound_hypothetical_100B_per_cycle=q(
            useful, max(MACS*ceildiv(k*n*b_word_bytes,100),useful)),
        scope="Source-derived architectural upper bound, not simulation, target memory performance, or whole-block utilization. No changes to datatype, iDMA, or Matrix.")


def evaluate(root):
    j = json.loads(pinned(root,MAP_PATH,MAP_SHA))
    need(j['matrix_macs'] == MACS and j['hardware_executed'] is False and
         j['no_intermediate_preload'] is True and [p['profile'] for p in j['profiles']] == list(range(5)),
         "mapped hardware/profile contract")
    for name,sha in SOURCE_PINS.items():
        pinned(root, f'{SOURCE_DIR}/{name}', sha)
    rows = []
    for p in j['profiles']:
        tables = p['segments'][:2]
        need([x['name'] for x in tables] == ['command','descriptor']
             and all(x['readonly'] is True for x in tables), "table roles")
        cmd, desc = (pinned(root,x['file'],x['sha256'],x['bytes']) for x in tables)
        row = extract(p,cmd,desc)
        width = 4 if row['profile'] == 0 else 2
        row['dense_feeder_envelope'] = streaming_envelope(row['m'],row['n'],row['k'],width,width,
            row['a_base_alignment_mod_1k'], row['weight_base_alignment_mod_1k'])
        rows.append(row)
    return dict(schema="hetero_pc1_static_mac_contract_v1", map_sha256=MAP_SHA,
                physical_mac_slots_per_cycle=MACS, source_sha256=SOURCE_PINS, hardware_executed=False,
                pc1_numeric_pass=False, whole_block_utilization=None, weight_payload_bytes_read=False,
                notes="Shape-derived targets and PC1-only cycle budgets, not timing predictions or MAC measurements. For original replay accept PC1 only after typed successful ordered PC0/PC1 retirement; validate live commits separately. Complete-block utilization must use full launch-to-terminal cycles, not these budgets.",
                rows=rows)

if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--root', required=True, type=Path)
    print(json.dumps(evaluate(p.parse_args().root.resolve()),indent=2,sort_keys=True))
