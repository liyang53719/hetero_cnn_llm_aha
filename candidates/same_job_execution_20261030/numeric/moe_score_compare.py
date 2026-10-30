"""Read-only full-M128 diagnostics, never a numerical acceptance contract.

Hardware P7-exp/stride8 probabilities need not equal official torch.softmax.
No tolerance, no replacement IDs, and no reference data is a DUT input.
"""
import hashlib
import json
import math
import os
import pathlib
import re
import struct

KEY = 'stage.mlp.gate.0.pre_topk_probs'
SIZE = 128 * 256 * 4

def need(ok, message):
    if not ok:
        raise ValueError(message)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def stable_bytes(path, size, expected_sha=None):
    path = pathlib.Path(path)
    need(path.is_file() and not path.is_symlink(), 'regular observation file')
    before = path.stat()
    need(before.st_size == size, 'exact observation byte count')
    data = path.read_bytes()
    after = path.stat()
    need((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
         (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'observation changed while reading')
    need(len(data) == size, 'complete read')
    actual_sha = digest(data)
    if expected_sha is not None:
        need(actual_sha == expected_sha, 'observation SHA256 mismatch')
    # Re-read verifies the reported hash refers to stable bytes, not a size-only file.
    need(digest(path.read_bytes()) == actual_sha, 'observation changed after reading')
    return data

def reference_probabilities(root, result, profile):
    need(result['profile']['profile'] == profile and profile in (3, 4), 'reference profile')
    need(result['status'] == 'CAPTURED_FRESH_OFFICIAL_FULL_BLOCK_REFERENCE_ONLY' and
         result['complete_block_tokens'] == 128 and result['exact_baseline_observer_output_equal'] is True and
         result['hardware_executed'] is False and result['numerical_comparison_with_hardware'] is False,
         'complete independent reference')
    need(result['router_policy'] == 'UNMODIFIED_OFFICIAL_TORCH_TOPK' and
         result['raw_router_score_observation'] == 'ORIGINAL_FORWARD_LOCAL_RETURN_READONLY_PROFILE' and
         result['no_reference_outputs_or_router_ids_allowed_in_hardware_stimulus'] is True,
         'unmodified independent observer contract')
    record = result['tensor_records'][KEY]
    need(record['shape'] == [128, 256] and record['dtype'] == 'torch.float32' and record['bytes'] == SIZE,
         'full reference FP32 shape/dtype/bytes')
    rel = pathlib.PurePosixPath(record['file'])
    need(not rel.is_absolute() and '..' not in rel.parts and rel.parts[0] == 'reference_only',
         'raw probability reference_only path required')
    base=pathlib.Path(root).resolve()
    path=base
    for part in rel.parts:
        path=path/part
        need(not path.is_symlink(),'reference symlink component')
    need(path.resolve().is_relative_to(base/'reference_only'), 'reference escape')
    return stable_bytes(path, SIZE, record['sha256'])

def probabilities(data):
    need(len(data) == SIZE, 'full128x256 FP32 coverage')
    # Preserve original words, including NaN/Inf/negative values; never repair.
    return [x[0] for x in struct.iter_unpack('<I', data)]

def value_counts(words, values):
    return dict(nan=sum(math.isnan(x) for x in values),
                positive_infinity=sum(x == math.inf for x in values),
                negative_infinity=sum(x == -math.inf for x in values),
                negative_finite=sum(math.isfinite(x) and x < 0 for x in values),
                negative_zero=sum(x == 0x80000000 for x in words),
                above_one_finite=sum(math.isfinite(x) and x > 1 for x in values))

def diagnostic(actual, reference):
    need(len(actual) == len(reference) and len(actual) % 4 == 0, 'diagnostic shape')
    aw = [x[0] for x in struct.iter_unpack('<I', actual)]
    rw = [x[0] for x in struct.iter_unpack('<I', reference)]
    af = [x[0] for x in struct.iter_unpack('<f', actual)]
    rf = [x[0] for x in struct.iter_unpack('<f', reference)]
    mismatch = [i for i, (a, r) in enumerate(zip(aw, rw)) if a != r]
    finite = [i for i, (a, r) in enumerate(zip(af, rf)) if math.isfinite(a) and math.isfinite(r)]
    # Monotonic IEEE sign-magnitude ordering with +/-0 collapsed numerically.
    # Bitwise mismatches still distinguish zero signs and every NaN payload.
    def ordered(word):
        magnitude=word & 0x7fffffff
        return 0x80000000-magnitude if word & 0x80000000 else 0x80000000+magnitude
    return dict(status='BITWISE_MISMATCH_DIAGNOSTIC' if mismatch else 'BITWISE_MATCH_DIAGNOSTIC',
                elements=len(aw), bytes=len(actual), byte_mismatches=sum(a != r for a, r in zip(actual, reference)),
                element_mismatches=len(mismatch), first_mismatch_element=next(iter(mismatch), None),
                finite_pair_count=len(finite), nonfinite_pair_count=len(aw)-len(finite),
                actual_value_counts=value_counts(aw,af), reference_value_counts=value_counts(rw,rf),
                max_absolute_error=max((abs(af[i]-rf[i]) for i in finite), default=None),
                max_ulp_distance=max((abs(ordered(aw[i])-ordered(rw[i])) for i in finite), default=None),
                ulp_policy='FINITE_PAIRS_ONLY_IEEE_SIGN_ORDER_PLUS_MINUS_ZERO_DISTANCE_ZERO_NAN_INF_EXCLUDED_AND_COUNTED',
                actual_sha256=digest(actual), reference_sha256=digest(reference),
                acceptance='DIAGNOSTIC_ONLY_NO_APPROVED_RAW_FP32_FAILURE_CONTRACT')


def selected_diagnostics(actual, reference, route_bytes, official_ids):
    need(len(route_bytes) == 8192 and len(official_ids) == 8192, 'full128x8 selected IDs')
    hardware = []
    for i, (word,) in enumerate(struct.iter_unpack('<Q', route_bytes)):
        need(word >> 41 == 0 and ((word >> 34) & 127) == i//8 and ((word >> 31) & 7) == i%8,
             'actual route token/rank/reserved')
        hardware.append((word >> 23) & 255)
    official = [x[0] for x in struct.iter_unpack('<q', official_ids)]
    need(all(0 <= x < 256 for x in official), 'official selected ID range')
    for ids in (hardware, official):
        need(all(len(set(ids[t*8:t*8+8])) == 8 for t in range(128)), 'unique selected IDs')
    def gather(data, ids):
        return b''.join(data[(i//8*256+e)*4:(i//8*256+e+1)*4] for i, e in enumerate(ids))
    return dict(observation_scope='DERIVED_ID_CORRESPONDENCE_NOT_CAPTURED_SELECTOR_OUTPUT',hardware_id_correspondence=diagnostic(gather(actual, hardware), gather(reference, hardware)),
                official_id_correspondence=diagnostic(gather(actual, official), gather(reference, official)),
                selected_id_mismatches=sum(a != r for a, r in zip(hardware, official)),
                tie_contract='PENDING_USER_SMALL_ID_ACCEPTANCE_UNMODIFIED_TORCH_TOPK')

def observe(directory, log, profile, reference, route_bytes, official_ids):
    need(profile in (3, 4), 'MoE profile only')
    lines = [line for line in log.splitlines() if line.startswith('HOST_ROUTER_RAW_SCORE_V1')]
    need(len(lines) == 1, 'one raw probability coverage receipt')
    match = re.fullmatch(r'HOST_ROUTER_RAW_SCORE_V1 profile=(\d+) transaction=(\d+) owner=(\d+) values=32768 bytes=131072 dtype=FP32 source=SELECTION_INPUT_FIRE terminal=CLEAN coverage=EXACT_ONCE', lines[0])
    need(match is not None, 'exact raw probability shape/dtype/coverage receipt')
    p, transaction, owner = map(int, match.groups())
    need(p == profile and transaction == 0 and 0 < owner < 0xffffffff, 'reset single-launch transaction/profile or owner bounds')
    need(sum(line.startswith('COMPLETE_ORIGINAL_HOST_DDR_REPLAY profile='+str(profile)+' ') for line in log.splitlines()) == 1,
         'unique clean whole-block terminal')
    need(pathlib.Path(directory).is_dir() and not pathlib.Path(directory).is_symlink(),'regular fresh observation directory')
    actual = stable_bytes(pathlib.Path(directory)/'router_selection_scores.fp32.actual.bin', SIZE)
    probabilities(actual); probabilities(reference)
    result=dict(status='COMPARED_DIAGNOSTIC_ONLY', shape=[128, 256], dtype='FP32_LE', coverage='EXACT_ONCE_32768',
                transaction=transaction, observed_owner_sequence=owner, owner_identity_basis='PINNED_SELECTION_COMMAND_AND_COLLECTOR_EXACT_ONCE_STABILITY_NOT_INDEPENDENT_EXPECTED_OWNER', owner_evidence_scope='SAME_LAUNCH_HARDWARE_INTERNAL_CONSISTENCY_NOT_EXTERNAL_PREAUTHORIZATION', full_probabilities=diagnostic(actual, reference),
                selected_probabilities=selected_diagnostics(actual, reference, route_bytes, official_ids),
                numerical_pass=False, arithmetic_note='HARDWARE_P7_EXP_STRIDE8_VS_OFFICIAL_TORCH_SOFTMAX_NO_NEW_TOLERANCE')
    try:
        result['actual_selected_output']=selected_output(directory,log,profile,transaction,owner,actual,reference,route_bytes,official_ids)
    except (ValueError,OSError) as error:
        result['actual_selected_output']={'status':'INCOMPLETE','error':str(error),'error_class':type(error).__name__}
    return result


def selected_output(directory, log, profile, transaction, owner, actual_input, reference, route_bytes, official_ids):
    """Read actual selection.out.fire bytes; never synthesize output from input."""
    lines=[line for line in log.splitlines() if line.startswith('HOST_ROUTER_SELECTED_SCORE_V2')]
    need(len(lines)==1,'one actual selected output coverage receipt')
    marker=(f'HOST_ROUTER_SELECTED_SCORE_V2 profile={profile} transaction={transaction} owner={owner} '
            'values=1024 score_bytes=4096 id_bytes=4096 dtype=FP32 index_dtype=UINT32 '
            'source=SELECTION_OUTPUT_FIRE terminal=CLEAN coverage=EXACT_ONCE')
    need(lines[0]==marker,'same-round selected output shape/dtype/coverage/identity')
    directory=pathlib.Path(directory)
    need(directory.is_dir() and not directory.is_symlink(),'regular fresh selected output directory')
    score_bytes=stable_bytes(directory/'router_selected_scores.fp32.actual.bin',4096)
    id_bytes=stable_bytes(directory/'router_selected_ids.u32.actual.bin',4096)
    ids=[x[0] for x in struct.iter_unpack('<I',id_bytes)]
    need(all(0<=x<256 for x in ids),'actual selected ID range')
    need(all(len(set(ids[t*8:t*8+8]))==8 for t in range(128)),'actual selected IDs unique per token')
    need(len(actual_input)==SIZE and len(reference)==SIZE,'selected correspondence full probability matrices')
    need(len(route_bytes)==8192 and len(official_ids)==8192,'selected correspondence full ID matrices')
    route_ids=[]
    for i,(word,) in enumerate(struct.iter_unpack('<Q',route_bytes)):
        need(word>>41==0 and ((word>>34)&127)==i//8 and ((word>>31)&7)==i%8,'route ordering for selected output')
        route_ids.append((word>>23)&255)
    official=[x[0] for x in struct.iter_unpack('<q',official_ids)]
    need(all(0<=x<256 for x in official),'official ID range for selected output')
    need(all(len(set(official[t*8:t*8+8]))==8 for t in range(128)),'official IDs unique per token')
    def gather(matrix, selected_ids=ids):
        return b''.join(matrix[(i//8*256+expert)*4:(i//8*256+expert+1)*4] for i,expert in enumerate(selected_ids))
    return dict(status='COMPARED_ACTUAL_SELECTION_OUTPUT_DIAGNOSTIC_ONLY',
                observation_scope='ACTUAL_SELECTION_OUTPUT_FIRE_NOT_RECONSTRUCTED',
                shape=[128,8],score_dtype='FP32_LE',id_dtype='UINT32_LE',score_bytes=4096,id_bytes=4096,
                score_sha256=digest(score_bytes),id_sha256=digest(id_bytes),
                transaction=transaction,observed_owner_sequence=owner,coverage='EXACT_ONCE_1024',
                input_output_score_consistency=diagnostic(score_bytes,gather(actual_input)),
                official_probability_at_actual_selected_id=diagnostic(score_bytes,gather(reference)),
                official_selected_probability_by_rank=diagnostic(score_bytes,gather(reference,official)),
                official_selected_reference_origin='INDEX_SAME_OFFICIAL_CAPTURED_FULL_FP32_PROBS_BY_UNMODIFIED_OFFICIAL_TOPK_IDS',
                selected_vs_route_id_mismatches=sum(a!=b for a,b in zip(ids,route_ids)),
                selected_vs_official_id_mismatches=sum(a!=b for a,b in zip(ids,official)),
                internal_consistency_is_not_official_reference_pass=True,numerical_pass=False)
