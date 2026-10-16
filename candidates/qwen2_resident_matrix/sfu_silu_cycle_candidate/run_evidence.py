"""Reproduce bounded arithmetic/schedule evidence, without any native/RTL job."""
import argparse
import hashlib
import json
from pathlib import Path
import random

from .arithmetic import HERE, ROOT, check_sources, ref_bf, rn
from .model import Configuration, Request
from .test_model import reference, run


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


ORIGINAL_FULL_REPORT_SHA256 = 'b58b8de6ecfc301b9b18f6128ceea4ef9cdbeb5f109714443a23a974107c6ebc'
ORIGINAL_RESULTS_SHA256 = '553f294e20d95907e4de92e73627a51fde6d93f72bc49676ea71199497fc1843'


def collect():
    rng = random.Random(20261016)
    cases = {
        'zero_full_exp_div25': ((0,) * 16, (0x3f800000,) * 16),
        'one_full_exp_div26': ((0x3f800000,) * 16, (0x3f800000,) * 16),
        'cutoff_div25': ((0x42a00000,) * 16, (0x3f800000,) * 16),
        'mixed_boundaries': ((0, 0x80000000, 1, 0x80000001, 0x007fffff, 0x00800000,
            0x429fffff, 0x42a00000, 0x42a00001, 0xc29fffff, 0xc2a00000, 0xc2a00001,
            0x7f7fffff, 0xff7fffff, 0x3f800000, 0xbf800000), (0x3f800000,) * 16)}
    for i in range(12):
        cases['finite_bf16_' + str(i)] = (
            tuple((rng.randrange(0x7f80) | rng.randrange(2) << 15) << 16 for _ in range(16)),
            tuple(ref_bf(rn(rng.randrange(-8, 9))) for _ in range(16)))
    results = []
    compared_nodes = compared_phases = error_responses = 0
    for name, (gate, up) in cases.items():
        q = Request(20261016, gate, up)
        for profile in ('LegacyV0', 'Qwen2OfficialBf16V2'):
            expected, exp_trace = reference(q, profile)
            for schedule, option in [('legacy_wrapper', 0), ('microsequence', 0), ('microsequence', 16)]:
                configuration = Configuration(schedule, option, profile)
                model, response, visible = run(q, configuration, stall=7)
                phases = [{k: v for k, v in p.items() if k != 'edge'} for p in model.phase_trace]
                if phases != expected or response.error != expected[-1]['error'] or response.value != expected[-1]['value']:
                    raise ValueError('original recipe mismatch')
                for lane in range(16):
                    actual = [(t['operation'], t['a'], t['b'], t['bits']) for t in model.trace
                              if t['phase'] == 0 and t['lane'] == lane]
                    if actual != exp_trace[lane]:
                        raise ValueError('original intermediate exp node mismatch')
                    compared_nodes += len(actual)
                compared_phases += 16 * len(phases)
                error_responses += response.error
                results.append(dict(case=name, configuration=configuration.__dict__,
                    request_sha256=digest(q.__dict__), response=response.__dict__,
                    first_response_visible_edge=visible, response_ack_edge=visible + 7,
                    next_request_eligible_edge=visible + 8, input_accept_edge=0,
                    counts=dict(sorted(model.counts.items())), phase_trace=model.phase_trace,
                    all_node_trace_sha256=digest(model.trace)))
    own = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(HERE.iterdir())
           if p.suffix in ('.py', '.json', '.md') and p.name not in ('EVIDENCE.json', 'review.json')}
    return dict(schema=1, status='PASS_BOUNDED_SOFTWARE_CANDIDATE',
        scope='exact original recipe and source counter model only, not RTL or useful-wall MAC acceptance',
        input_vectors=len(cases), tested_configurations=6, completed_transactions=len(results),
        exp_node_comparisons=compared_nodes, phase_lane_comparisons=compared_phases,
        expected_error_responses=error_responses, unexpected_errors=0,
        source_pins=check_sources(), candidate_sha256=own,
        frozen_source_files_modified=False, native_or_rtl_jobs_run=False,
        full_block_accepted=False, mac90_accepted=False, results=results)


def summarize(full):
    """One-way, bounded publication projection; never encode tensor payloads.

    Counter values and phase capture edges are ordinary scheduling metadata.
    Only hashes of arithmetic input/output/phase/node data leave collect().
    """
    if digest(full['results']) != ORIGINAL_RESULTS_SHA256:
        raise ValueError('original96-transaction numerical/schedule results changed')
    names = sorted({name for result in full['results'] for name in result['counts']})
    configurations, requests, numerics, counters, transactions = [], [], [], [], []

    def intern(table, entry):
        if entry not in table:
            table.append(entry)
        return table.index(entry)

    for result in full['results']:
        phase_values = [{k: v for k, v in phase.items() if k != 'edge'}
                        for phase in result['phase_trace']]
        numeric = dict(case=result['case'], profile=result['configuration']['numerical_profile'],
                       phase_sha256=[digest(p) for p in phase_values],
                       response_sha256=digest(result['response']),
                       error=result['response']['error'], failed_phase=result['response']['failed_phase'])
        transactions.append(dict(
            request=intern(requests, dict(case=result['case'], sha256=result['request_sha256'])),
            configuration=intern(configurations, result['configuration']),
            numerical=intern(numerics, numeric),
            counters=intern(counters, [result['counts'].get(name, 0) for name in names]),
            first_response_visible_edge=result['first_response_visible_edge'],
            response_ack_edge=result['response_ack_edge'],
            next_request_eligible_edge=result['next_request_eligible_edge'],
            input_accept_edge=result['input_accept_edge'],
            phase_capture_edges=[p['edge'] for p in result['phase_trace']],
            full_node_trace_sha256=result['all_node_trace_sha256']))
    # Whitelist, rather than recursively retaining unknown future full-report data.
    retained = ('status', 'scope', 'input_vectors', 'tested_configurations',
                'completed_transactions', 'exp_node_comparisons', 'phase_lane_comparisons',
                'expected_error_responses', 'unexpected_errors', 'source_pins',
                'candidate_sha256', 'frozen_source_files_modified', 'native_or_rtl_jobs_run',
                'full_block_accepted', 'mac90_accepted')
    return dict(schema=2, publication='HASHES_AND_SCHEDULE_METADATA_ONLY',
                original_full_report_sha256=ORIGINAL_FULL_REPORT_SHA256,
                original_results_canonical_sha256=ORIGINAL_RESULTS_SHA256,
                regenerated_full_report_canonical_sha256=digest(full),
                **{key: full[key] for key in retained}, configurations=configurations,
                requests=requests, numerical_groups=numerics, counter_names=names,
                counter_sets=counters, transactions=transactions)


def write_evidence(*, full_output=None):
    if full_output is not None:
        full_output = Path(full_output).resolve()
        if full_output.is_relative_to(ROOT):
            raise ValueError('full arithmetic report must remain outside the publication repository')
        if full_output.exists():
            raise ValueError('refusing to overwrite an existing local full report')
    full = collect()
    if full_output is not None:
        with full_output.open('x') as stream:
            stream.write(json.dumps(full, indent=2, sort_keys=True) + '\n')
    summary = summarize(full)
    (HERE / 'EVIDENCE.json').write_text(json.dumps(summary, sort_keys=True, separators=(',', ':')) + '\n')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--full-output', type=Path,
                        help='optional new local/CI report path OUTSIDE the repository; never overwritten')
    summary = write_evidence(full_output=parser.parse_args().full_output)
    print(json.dumps({key: summary[key] for key in ('status', 'completed_transactions',
        'exp_node_comparisons', 'phase_lane_comparisons', 'expected_error_responses',
        'original_full_report_sha256')}, indent=2))
