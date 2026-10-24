"""Hash-only saved cold boundary check. Explicit JSON root map; no native imports.

This is not a full-block completion seal. Inputs and historical receipts stay private;
only the already reviewed selected artifact hashes and actual input edges are checked.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare_chunk import pin
from suffix_case import need

HERE = Path(__file__).resolve().parent


def check(roots):
    spec = json.loads((HERE / 'cold_chain_pins.json').read_text())
    artifacts = spec['observed_artifacts']
    need(set(roots) == {key.split('/')[0] for key in artifacts}, 'exact explicit root map required')
    roots = {key: Path(value).resolve(strict=True) for key, value in roots.items()}
    def path(relative):
        alias, name = relative.split('/', 1); root = roots[alias]; result = (root / name).resolve(strict=True)
        need(root in result.parents, 'artifact outside explicit root')
        return result
    for relative, recorded in artifacts.items():
        need(pin(path(relative)) == recorded, 'selected artifact identity: ' + relative)
    summaries = {stage: json.loads(path(location + 'summary.json').read_text())
                 for stage, location in spec['stage_locations'].items()}
    for edge in spec['actual_boundary_edges']:
        need(summaries[edge['consumer']]['input_sha256'][edge['consumer_input_index']] == edge['actual_sha256'] ==
             spec['outputs'][edge['producer']]['sha256'], 'actual predecessor/consumer identity')
    for relative, recorded in artifacts.items():
        need(pin(path(relative)) == recorded, 'selected artifact changed: ' + relative)
    return dict(scope=spec['scope'], input_chain_checked_edges=len(spec['actual_boundary_edges']),
        selected_artifact_pins=len(artifacts), before_after_selected_hashes_match=True,
        original_execution_status='UNKNOWN', completion_seal=False, full_block_acceptance=False,
        single_resident_full_block_lifecycle=False, state_committed=False, history_committed=False,
        generation_advanced=False, native_adaptation='TEMP_NOT_EXECUTED', prep_threshold_assigned=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--roots', type=Path, required=True, help='JSON object mapping named bundles to explicit private roots')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); result = check(json.loads(args.roots.read_text()))
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True); stream.write('\n')
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
