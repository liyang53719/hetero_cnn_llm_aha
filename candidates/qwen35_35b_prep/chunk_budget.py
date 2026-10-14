"""Integer transport/operation prediction, not hardware cycle evidence."""
from collections import Counter

def closed_counts(tokens, key_dim, value_dim, heads=32, guarded=True, cold=True, matmul_policy="row1_streaming"):
    if not (type(tokens) is int and 1 <= tokens <= 128 and
            type(key_dim) is int and key_dim in range(16,129,16) and
            type(value_dim) is int and value_dim in range(32,129,32) and
            type(heads) is int and 1 <= heads <= 32 and
            type(guarded) is bool and type(cold) is bool):
        raise ValueError("bounded chunk transport geometry")
    if matmul_policy not in ("row1_streaming", "row4_shared_1kib"):
        raise ValueError("bounded chunk matmul policy")
    b, d = key_dim // 16, value_dim // 16
    chunks = (tokens + 63) // 64
    s = key_dim * d
    t = 832 + 576*b + 512*d + 3*s
    a = (2656 + 3004*b + 512*key_dim + 6908*d
         + 128*d*(b+key_dim) + 71*s)
    q = (512*key_dim + 2016*(b+d) + 128*d*key_dim
         + 4096*d + 64*s)
    z = 13 if guarded else 1
    hc = heads * chunks
    add16 = 64*(b+d) + 128*d + s
    add1 = 64*z + 2144
    mul16 = 256*b + 64*d + 512 + s
    out = Counter(
        source_read_requests=heads*(tokens*(1+2*b+d)+(0 if cold else s)),
        scratch_read_requests=heads*(s+chunks*a+tokens*d),
        scratch_write_requests=heads*(s+chunks*t),
        state_write_requests=heads*s,
        output_write_requests=heads*tokens*d//2,
        vector_add_issues=hc*(q+add16+add1),
        vector_mul_issues=hc*(q+mul16),
        vector_add_lane_ops=hc*(16*(q+add16)+add1),
        vector_mul_lane_ops=16*hc*(q+mul16),
        host_mul_add=hc*q,
        host_single=hc*(add16+add1+mul16),
        exp_calls=hc*2209,
        cumsum_terms=hc*64,
        cumsum_add_issues=hc*64*z,
        upper_triangle_masked=hc*2016,
        chunks_started=hc,
        chunks_completed=hc,
    )
    if matmul_policy == "row4_shared_1kib":
        # Six matmuls: only B loads change; all output rows are multiples of four.
        b_reads = 512*key_dim + 128*d*key_dim + 4096*d + 64*s
        assert b_reads % 4 == 0
        out["scratch_read_requests"] -= hc * (3*b_reads//4)
    return finish(out)


def finish(c):
    c['read_requests'] = c['source_read_requests'] + c['scratch_read_requests']
    c['write_requests'] = sum(c[n] for n in (
        'scratch_write_requests', 'state_write_requests', 'output_write_requests'))
    c['write_acks'] = c['write_requests']
    c['memory_responses'] = c['read_requests'] + c['write_requests']
    c['scratch_ack_bytes'] = 64*c['scratch_write_requests']
    c['read_bytes'] = 64*c['read_requests']
    c['write_bytes'] = 64*c['write_requests']
    c['source_read_bytes'] = 64*c['source_read_requests']
    c['scratch_read_bytes'] = 64*c['scratch_read_requests']
    c['output_bytes'] = 64*c['output_write_requests']
    c['state_bytes'] = 64*c['state_write_requests']
    c['scratch_ddr_bytes'] = 64*c['scratch_write_requests']
    c['owner_results'] = 1
    c['driver_ticks_no_stall'] = 2*c['memory_responses'] + 1
    c['owner_result_model_ticks_no_stall'] = 2*c['memory_responses']
    c['single_host_calls_without_batching'] = c['vector_add_issues'] + c['vector_mul_issues']
    return dict(sorted(c.items()))

