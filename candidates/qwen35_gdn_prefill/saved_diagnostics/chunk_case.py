"""Bounded head0 cases and byte mappings only; no owner or native imports."""

TOKENS = (64, 128)
PREP_ROW_BYTES = 25600
WIDTH = 128
STATE_BYTES = WIDTH * WIDTH * 4
CARRY_READ_BEATS = {'predict_matmul': 65536, 'inter_matmul': 65536, 'state_decay': 1024}


def case(tokens=64):
    if type(tokens) is not int or tokens not in TOKENS:
        raise ValueError('tokens must be 64 or 128')
    return dict(tokens=tokens, chunks=tokens // 64, elements=tokens * WIDTH,
                schema=f'qwen35_head0_m{tokens}_isolated_v1', state_oracle=tokens == 128,
                driver_seconds=60 if tokens == 64 else 90,
                outer_seconds=75 if tokens == 64 else 110,
                cleanup_reserve_seconds=15 if tokens == 64 else 20)


def plan_case(plan):
    selected = case(plan['policy']['tokens'])
    if plan['schema'] != selected['schema']:
        raise ValueError('case/schema mismatch')
    if selected['state_oracle'] and not plan.get('reference_state_slice'):
        raise ValueError('M128 requires the after128 state oracle')
    if not selected['state_oracle'] and plan.get('reference_state_slice'):
        raise ValueError('M64 has no official after64 state oracle')
    for field, expected in (('cpu_seconds', selected['driver_seconds']),
                            ('driver_wall_seconds', selected['driver_seconds']),
                            ('outer_wall_seconds', selected['outer_seconds'])):
        if plan['limits'][field] != expected:
            raise ValueError('case resource limit mismatch: ' + field)
    return selected


def head0_output(reference, tokens):
    case(tokens)
    if len(reference) != 128 * 16 * WIDTH * 2:
        raise ValueError('official output must be [1,128,16,128] BF16')
    return b''.join(reference[row * 16 * WIDTH * 2:(row * 16 * WIDTH + WIDTH) * 2]
                    for row in range(tokens))


def prep_rows(prep, tokens):
    case(tokens)
    if len(prep) != 128 * PREP_ROW_BYTES:
        raise ValueError('saved Prep must contain exactly 128 complete rows')
    return prep[:tokens * PREP_ROW_BYTES]


def head0_state(state, final_cache):
    if len(state) != 16 * STATE_BYTES or state != final_cache:
        raise ValueError('official after128 state/final-cache extent or identity mismatch')
    return state[:STATE_BYTES]


def validate_carry(chunks_completed, observed):
    if chunks_completed != 2 or observed != CARRY_READ_BEATS:
        raise ValueError('actual two-chunk carry-read evidence required')
