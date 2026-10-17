#!/usr/bin/env python3
"""Source-constrained necessary bounds, never an RTL performance prediction."""
from fractions import Fraction
from pathlib import Path
import argparse, hashlib, json

USEFUL = 6_014_828_544
MACS = 4096
IDEAL = USEFUL // MACS
M = 128
PAIRS = 12 * M * (M + 1) // 2
ROWS = 12 * M
VECTORS = M * 8960 // 16
HIDDEN = 1536
FFN = 8960
KV = 256
FRONT_DENSE_ISSUES = M * HIDDEN * (HIDDEN + 2*KV + HIDDEN) // MACS
GATE_UP_ISSUES = 2 * M * HIDDEN * FFN // MACS
DOWN_ISSUES = M * FFN * HIDDEN // MACS
DENSE_ISSUES = FRONT_DENSE_ISSUES + GATE_UP_ISSUES + DOWN_ISSUES
PROFILES = ('raw_scalar', 'qk16_only', 'packed_qk_pv')


def control_trace(operation, divider_latency=25):
    """No arithmetic: source FSM edge labels from request acceptance to reaccept."""
    if operation in ('add','mul'):
        return ['accept','normal','done_ack','next_accept']
    if operation == 'cutoff_exp':
        return ['accept','expScale_cutoff','done_ack','next_accept']
    if operation == 'full_exp':
        return (['accept','expScale','expFloor','expFraction'] +
                ['expMul','expAdd']*7 + ['expFinish','done_ack','next_accept'])
    if operation == 'div' and type(divider_latency) is int and divider_latency in (25,26):
        return (['accept','divIssue'] + ['divWait']*(divider_latency-1) +
                ['divider_return_capture','done_ack','next_accept'])
    raise ValueError('original source control operation/normal divider latency required')


def pinned_file_matches(path, expected):
    return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected


def gate(percent):
    if percent not in (80, 90):
        raise ValueError('only fixed 80/90 gates')
    exact = Fraction(USEFUL * 100, MACS * percent)
    return {'numerator': exact.numerator, 'denominator': exact.denominator,
            'max_integer_cycles': exact.numerator // exact.denominator}


def counts(profile):
    if profile not in PROFILES:
        raise ValueError('unknown algorithm, no implicit profile substitution')
    qk_groups = 12 * sum((q + 15) // 16 for q in range(1, M + 1))
    qk = PAIRS * 8 if profile == 'raw_scalar' else qk_groups * 8
    pv = 2 * sum(range(1, M + 1)) if profile == 'packed_qk_pv' else PAIRS * 8
    norm = PAIRS if profile == 'packed_qk_pv' else 8 * PAIRS
    return dict(pairs=PAIRS, rows=ROWS, fold_add=16 * PAIRS,
                score_scale=PAIRS, subtract=PAIRS, ordered_sum=PAIRS,
                normalize=norm, exp=PAIRS, reciprocal=ROWS,
                qk_issues=qk, pv_issues=pv, dense_issues=DENSE_ISSUES)


def scalar_bound(profile, full_exp=None):
    """Map algorithm onto ORIGINAL one Scalar, with no other work overlapping.

    Inter-acceptance minima: Add/Mul 3; exp cutoff/full 3/20; normal
    options0 division 28 (25 divider + issue/done boundary 3).
    Last response ACK precedes next possible acceptance by one edge: subtract
    ONE from the service-slot sum. Owner resume/feed/holds only add latency.
    Full-exp minimum R follows from at least one exp(0) per finite row.
    """
    c = counts(profile)
    if full_exp is None:
        full_exp = ROWS
    if type(full_exp) is not int or not ROWS <= full_exp <= PAIRS:
        raise ValueError('finite successful rows require R <= full_exp <= P')
    primitive = sum(c[k] for k in ('fold_add', 'score_scale', 'subtract',
                                  'ordered_sum', 'normalize'))
    slots = 3 * primitive + 3 * (PAIRS-full_exp) + 20 * full_exp + 28 * ROWS
    service = slots - 1
    matrix = c['qk_issues'] + c['pv_issues'] + DENSE_ISSUES
    wall_lower_bound = service + matrix
    return dict(profile=profile, counts=c, full_exp_count=full_exp,
                full_exp_condition=('at_least_one_per_row' if full_exp == ROWS else 'explicit_branch_count'),
                scalar_interacceptance_slot_sum=slots,
                scalar_service_lower_bound=service,
                serial_matrix_issue_lower_bound=matrix,
                serial_wall_lower_bound=wall_lower_bound,
                upper_useful_utilization=ratio(Fraction(IDEAL, wall_lower_bound)),
                conditions=['finite successful attention', 'original one Scalar options0',
                            'no overlap between scalar service and Matrix/Dense issues',
                            'algorithm-specific normalization count',
                            'each Matrix issue at least one cycle'],
                omitted_costs=['DMA and stalls', 'bank service and conflicts',
                               'max/BF16/controller overhead', 'FFN SiLU', 'final ACK tail'],
                evidence_kind='source_necessary_lower_bound', rtl_measured=False,
                accepted_80=False, accepted_90=False)


def ratio(x):
    return dict(numerator=x.numerator, denominator=x.denominator)


def silu_bounds(full_exp_vectors=None):
    # Global lane barrier: a vector is full if at least one lane is full.
    out = {'vectors': VECTORS, 'options0_divider_only': 25*VECTORS,
           'options16_divider_only': 14*VECTORS,
           'front_matrix_barrier': FRONT_DENSE_ISSUES + counts('packed_qk_pv')['qk_issues'] + counts('packed_qk_pv')['pv_issues'],
           'down_matrix_barrier': DOWN_ISSUES,
           'conditions': ['complete successful SiLU without early error exit',
                          'each vector executes normal finite nonzero-denominator division',
                          '16 dividers, unchanged numerical recipe',
                          'options16 is unverified datapath/STA configuration',
                          'barriers apply only while full front and Down barriers remain'],
           'rtl_measured': False}
    out['options0_with_front_down_lower_bound'] = (out['options0_divider_only'] +
                                                   out['front_matrix_barrier'] + DOWN_ISSUES)
    if full_exp_vectors is not None:
        if type(full_exp_vectors) is not int or not 0 <= full_exp_vectors <= VECTORS:
            raise ValueError('explicit vector branch count required')
        # Existing microsequence retains conversion state: 21 ALU + 1 floor
        # on full path; cutoff retains scale + denominator + three Mul.
        out['full_exp_vectors'] = full_exp_vectors
        out['nondivision_state_slots'] = 22*full_exp_vectors + 5*(VECTORS-full_exp_vectors)
        out['conditional_front_sfu_down_lower_bound'] = (out['front_matrix_barrier'] +
             max(out['nondivision_state_slots'], out['options16_divider_only']) + DOWN_ISSUES)
        out['conditions'].append('explicit full-exp VECTOR count; retained non-overlapped floor service state')
    return out


def validate_claim(claim):
    """This checker cannot certify RTL even if supplied a plausible cycle count."""
    if claim.get('evidence_kind') != 'source_necessary_lower_bound':
        raise ValueError('only source necessary bounds accepted; not RTL measurement')
    if any(claim.get(k) for k in ('rtl_measured', 'accepted_80', 'accepted_90',
                                  'ideal_feed_is_hardware', 'service_slots_are_wall_cycles')):
        raise ValueError('ideal supply/service slots cannot certify full-block RTL')
    return True


def verify_pins(roots):
    """Explicit consumer-local roots only; no fallback to author workspace."""
    manifest = json.loads(Path(__file__).with_name('SOURCE_PINS.json').read_text())
    needed = {item['root'] for item in manifest['files']} - {'bundle'}
    if not isinstance(roots, dict) or set(roots) != needed:
        raise ValueError('explicit source roots required: ' + ', '.join(sorted(needed)))
    roots = dict(roots, bundle=Path(__file__).resolve().parent)
    failures=[]
    for item in manifest['files']:
        relative=Path(item['path'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('source pin path must be relative and bounded')
        path=Path(roots[item['root']])/relative
        if not pinned_file_matches(path, item['sha256']):
            failures.append(item['root'] + ':' + item['path'])
    if failures:
        raise ValueError('source pins mismatch: ' + ', '.join(failures))
    return len(manifest['files'])


def report():
    profiles=[scalar_bound(p) for p in PROFILES]
    for p in profiles:
        validate_claim(p)
    return {'useful_macs':USEFUL, 'fixed_macs_per_cycle':MACS, 'ideal_cycles':IDEAL,
            'cycle_gates':{str(p):gate(p) for p in (80,90)}, 'profiles':profiles,
            'silu_unconditional':silu_bounds(),
            'silu_all_full_CONDITIONAL':silu_bounds(VECTORS),
            'measurement_boundary':'complete block launch through final completion ACK; DMA/stalls included',
            'packed_algorithm_evidence':'exact source-only composed M128 schedule pinned in bundle; not executed',
            'rtl_measured':False, 'accepted_80':False, 'accepted_90':False}

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--production-source', type=Path)
    parser.add_argument('--candidate-tree', type=Path)
    parser.add_argument('--qk16-source', type=Path)
    args=parser.parse_args()
    supplied = {'production_source': args.production_source,
                'candidate_tree': args.candidate_tree, 'qk16_source': args.qk16_source}
    if any(value is not None for value in supplied.values()) and not all(value is not None for value in supplied.values()):
        parser.error('source verification requires all three explicit source roots')
    output=report()
    output['source_pins_verified_count'] = verify_pins(supplied) if all(value is not None for value in supplied.values()) else None
    output['source_pins_manifest_sha256'] = hashlib.sha256(Path(__file__).with_name('SOURCE_PINS.json').read_bytes()).hexdigest()
    print(json.dumps(output,ensure_ascii=False,indent=2))
