"""Pure candidate for same-live cold-cache copy plus unchanged BF16 operator gates.

No IO, admission, artifact discovery, or whole-block verdict. Caller must obtain
expected commitments from its independently checked, sealed live execution.
"""
import hashlib
import re
import struct

TOKENS, HEADS, DIM = 128, 2, 128
WORDS = TOKENS * HEADS * DIM
SIZE = WORDS * 4
LIMITS = {'max_abs': 0.03125, 'mean_abs': 0.005}
LAYOUTS = {'k': 'TOKEN_HEAD_DIM_F32LE_BF16', 'v': 'TOKEN_HEAD_DIM_F32LE_BF16',
           'cache': 'K_THEN_V_TOKEN_HEAD_DIM_F32LE_BF16'}


def need(ok, message):
    if not ok:
        raise ValueError(message)


def digest(value):
    need(type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None,
         'invalid identity commitment')
    return value


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def values(raw, size):
    need(type(raw) is bytes and len(raw) == size, 'fixed complete payload required')
    words = struct.unpack('<' + 'I' * (size // 4), raw)
    need(all(w & 0xffff == 0 and w & 0x7f800000 != 0x7f800000 for w in words),
         'finite exact BF16 widening required')
    return struct.unpack('<' + 'f' * (size // 4), raw)


def token_major(head_major):
    # Exactly [1,2,128,128] -> [1,128,2,128]; no inferred layout.
    values(head_major, SIZE)
    return b''.join(head_major[(h*TOKENS+t)*DIM*4:(h*TOKENS+t+1)*DIM*4]
                    for t in range(TOKENS) for h in range(HEADS))


def compare(*, payloads, receipts, expected_run, expected_live_identity,
            expected_artifacts, official, official_commitments):
    """Validate identity/copy only; malformed evidence raises ValueError.

    Expected identities are trusted caller inputs, not derived from receipts here.
    official k is fixed head-major; official v is fixed token-major, committed by a separately
    reviewed new reference contract. This function cannot authenticate receipts.
    """
    need(type(expected_run) is str and bool(re.fullmatch('[A-Za-z0-9_-]{1,64}', expected_run)),
         'explicit admitted run identity')
    digest(expected_live_identity)
    for mapping in (payloads, receipts, expected_artifacts):
        need(type(mapping) is dict and set(mapping) == set(LAYOUTS), 'exact DUT roles')
    need(type(official) is dict and set(official) == {'k', 'v'}, 'exact official roles')
    need(type(official_commitments) is dict and set(official_commitments) == {'k', 'v'},
         'explicit reviewed official commitments')
    for role in LAYOUTS:
        raw = payloads[role]; size = SIZE * (2 if role == 'cache' else 1)
        values(raw, size)
        digest(expected_artifacts[role])
        need(sha(raw) == expected_artifacts[role], 'payload differs from admitted artifact')
        receipt = receipts[role]
        need(type(receipt) is dict and set(receipt) == {'role', 'run', 'live_identity', 'layout',
             'bytes', 'sha256', 'sealed', 'terminal', 'ack_bytes', 'ack_64b_beats', 'origin'}, 'exact completion receipt')
        need(receipt['role'] == role and receipt['run'] == expected_run and
             receipt['live_identity'] == expected_live_identity and receipt['layout'] == LAYOUTS[role],
             'same-live identity or layout mismatch')
        need(type(receipt['bytes']) is int and receipt['bytes'] == size and
             type(receipt['ack_bytes']) is int and receipt['ack_bytes'] == size and
             type(receipt['ack_64b_beats']) is int and receipt['ack_64b_beats'] == size // 64 and
             receipt['origin'] == ('SEALED_ACTUAL_KV_PHYSICAL_READBACK' if role == 'cache' else 'SEALED_ACTUAL_PRODUCER') and
             receipt['sealed'] is True and receipt['terminal'] is True and
             receipt['sha256'] == expected_artifacts[role], 'sealed terminal full ACK required')
    need(payloads['cache'] == payloads['k'] + payloads['v'], 'same-live cache copy corrupted')
    official_tokens = {}
    for role in ('k', 'v'):
        digest(official_commitments[role])
        need(type(official[role]) is bytes and sha(official[role]) == official_commitments[role],
             'reviewed official artifact mismatch')
        values(official[role], SIZE)
        official_tokens[role] = token_major(official[role]) if role == 'k' else official[role]
    return dict(scope='COLD_CACHE_IDENTITY_AND_COPY_ONLY',
        same_live_exact_copy=True,
        official_kv_exact_copy=payloads['cache'] == official_tokens['k'] + official_tokens['v'],
        numerical_acceptance_claimed=False,
        whole_block_acceptance_claimed=False, historical_run_upgraded=False)
