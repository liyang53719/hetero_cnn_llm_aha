"""Bounded head0/M64, head0/M128, and all16/M128 cases; no owner/native imports."""

TOKENS = (64, 128)
HEADS = (1, 16)
PREP_ROW_BYTES = 25600
WIDTH = 128
STATE_BYTES = WIDTH * WIDTH * 4
CARRY_READ_BEATS = {'predict_matmul': 65536, 'inter_matmul': 65536, 'state_decay': 1024}
ALL16_LIMITS = dict(address_space_bytes=1 << 30, sampled_rss_bytes=1 << 30,
                    cpu_seconds=600, driver_wall_seconds=600, outer_wall_seconds=660,
                    file_bytes=8 << 20, log_bytes=2 << 20, output_bytes=32 << 20,
                    minimum_disk_available_bytes=256 << 20, minimum_host_available_bytes=2 << 30)


def case(tokens=64, heads=1):
    if type(tokens) is not int or tokens not in TOKENS:
        raise ValueError('tokens must be 64 or 128')
    if type(heads) is not int or heads not in HEADS or (heads == 16 and tokens != 128):
        raise ValueError('heads must be 1 or 16; 16 requires tokens=128')
    label = 'head0' if heads == 1 else 'all16'
    return dict(tokens=tokens, heads=heads, label=label, chunks=heads * tokens // 64,
                elements=tokens * heads * WIDTH, state_bytes=heads * STATE_BYTES,
                schema=f'qwen35_{label}_m{tokens}_isolated_v1', state_oracle=tokens == 128,
                driver_seconds=600 if heads == 16 else (60 if tokens == 64 else 90),
                outer_seconds=660 if heads == 16 else (75 if tokens == 64 else 110),
                cleanup_reserve_seconds=60 if heads == 16 else (15 if tokens == 64 else 20),
                postflight_reserve_seconds=10 if heads == 16 else 5,
                job_addresses=(0x400000, 0x800000, 0xA00000, 0xC00000, 0x1000000) if heads == 16
                else (0x400000, 0x800000, 0x810000, 0x820000, 0x900000))


def plan_case(plan):
    selected = case(plan['policy']['tokens'], plan['policy']['heads'])
    if plan['schema'] != selected['schema']:
        raise ValueError('case/schema mismatch')
    if selected['state_oracle'] and not plan.get('reference_state_slice'):
        raise ValueError('M128 requires the after128 state oracle')
    if not selected['state_oracle'] and plan.get('reference_state_slice'):
        raise ValueError('M64 has no official after64 state oracle')
    expected_limits = (ALL16_LIMITS if selected['heads'] == 16 else
                       dict(cpu_seconds=selected['driver_seconds'],
                            driver_wall_seconds=selected['driver_seconds'],
                            outer_wall_seconds=selected['outer_seconds']))
    for field, expected in expected_limits.items():
        if plan['limits'][field] != expected:
            raise ValueError('case resource limit mismatch: ' + field)
    return selected


def output_slice(reference, tokens, heads=1):
    case(tokens, heads)
    if len(reference) != 128 * 16 * WIDTH * 2:
        raise ValueError('official output must be [1,128,16,128] BF16')
    if heads == 16:
        return reference
    return b''.join(reference[row * 16 * WIDTH * 2:(row * 16 * WIDTH + WIDTH) * 2]
                    for row in range(tokens))


def prep_rows(prep, tokens):
    case(tokens)
    if len(prep) != 128 * PREP_ROW_BYTES:
        raise ValueError('saved Prep must contain exactly 128 complete rows')
    return prep[:tokens * PREP_ROW_BYTES]


def state_slice(state, final_cache, heads=1):
    selected = case(128, heads)
    if len(state) != 16 * STATE_BYTES or state != final_cache:
        raise ValueError('official after128 state/final-cache extent or identity mismatch')
    return state[:selected['state_bytes']]


def validate_carry(chunks_completed, observed, heads=1):
    selected = case(128, heads)
    expected = (CARRY_READ_BEATS if heads == 1 else
                {str(head): CARRY_READ_BEATS for head in range(heads)})
    if chunks_completed != selected['chunks'] or observed != expected:
        raise ValueError('actual per-head two-chunk carry-read evidence required')


def validate_first_states(observed, heads=1):
    case(128, heads)
    if heads == 1:
        if not isinstance(observed, str) or not observed:
            raise ValueError('actual first-chunk state identity required')
    elif (not isinstance(observed, dict) or set(observed) != {str(h) for h in range(heads)}
          or not all(isinstance(value, str) and value for value in observed.values())):
        raise ValueError('actual first-chunk state identity required for every head')
