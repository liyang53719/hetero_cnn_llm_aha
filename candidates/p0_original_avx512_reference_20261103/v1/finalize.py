"""Bounded final source, imported-native, weight and generated-file recheck."""
import argparse
import json
from pathlib import Path
from fixture_gate import frozen, need, sha, strict_json, check_weight
from prepare_runtime import verify_files
from validate_source import verify_source


def main():
    ap = argparse.ArgumentParser()
    for name in ('repo', 'work', 'output'):
        ap.add_argument('--' + name, type=Path, required=True)
    ap.add_argument('--source-sha256', required=True)
    ap.add_argument('--runtime-sha256', required=True)
    args = ap.parse_args()
    verify_source(args.repo, args.source_sha256)
    f = frozen()
    runtime = args.work / 'runs/runtime/output'
    need(sha(runtime / 'RUNTIME_RECEIPT.json') == args.runtime_sha256, 'PRECHECK_PIN')
    receipt = strict_json(runtime / 'RUNTIME_RECEIPT.json')
    need(receipt['status'] == 'FRESH_VERIFIED_NOT_REFERENCE_QUALIFIED' and receipt['schema'] == 'P0_AVX512_FRESH_RUNTIME_V1' and receipt['observed_capability'] == 'AVX512' and receipt['threads'] == 4 and receipt['interop_threads'] == 1, 'PRECHECK_PIN')
    need(sha(runtime / 'python') == receipt['wrapper_sha256'] and sha(runtime / 'SOURCE_SIDECAR.json') == f['runtime_sidecar']['sha256'], 'PRECHECK_PIN')
    verify_files(runtime / 'site-packages', f['runtime_sidecar']['content'])
    weights = args.work / 'runs/weights/output'
    for pin in f['weights']:
        row = strict_json(weights / 'qwen2_1p5b' / (pin['name'] + '.receipt.json'))
        check_weight(row, weights / row['file'])
    reference = args.work / 'runs/reference/output'
    r = strict_json(reference / 'RESULT.json')
    need(set(r['tensor_records']) == set(f['frozen_fixture']['tensor_records']) and r['observed_module_calls'] == f['frozen_fixture']['observed_module_calls'] and r['forward_calls'] == 2 and r['exact_baseline_observer_output_equal'] is True, 'REFERENCE_INVENTORY')
    for name, pin in f['frozen_fixture']['tensor_records'].items():
        row = r['tensor_records'][name]
        need(all(row[key] == pin[key] for key in ('shape', 'dtype', 'bytes', 'sha256', 'file')), 'REFERENCE_HASH')
        path = reference / pin['file']
        need(path.stat().st_size == pin['bytes'] and sha(path) == pin['sha256'], 'REFERENCE_HASH')
    rope = args.work / 'runs/rope/output/rope_fp32.bin'
    pin = f['frozen_fixture']['rope1024']
    need(rope.stat().st_size == pin['bytes'] and sha(rope) == pin['sha256'], 'ROPE_HASH')
    verify_source(args.repo, args.source_sha256)
    args.output.mkdir(exist_ok=False)
    (args.output / 'RESULT.json').write_text(json.dumps({'status':'PASS_FINAL_RECHECK', 'weights':12, 'visible_tensors':25}) + '\n')

if __name__ == '__main__':
    main()
