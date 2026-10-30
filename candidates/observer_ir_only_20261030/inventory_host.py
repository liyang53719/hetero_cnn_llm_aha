"""Original full fresh-host identity, including Verilator bytes, without frontend execution."""
import argparse, hashlib, json, pathlib, sys

def main():
    p = argparse.ArgumentParser()
    for name in ('materialization', 'contract', 'java_home', 'verilator_root', 'compile_inventory', 'output'):
        p.add_argument('--' + name.replace('_', '-'), type=pathlib.Path, required=True)
    p.add_argument('--contract-sha256', required=True)
    a = p.parse_args()
    sys.path.insert(0, str(a.materialization))
    import fresh_host
    contract = fresh_host.load_contract(a.contract, a.contract_sha256)
    fresh_host.validate_compile_inventory(json.loads(a.compile_inventory.read_text()))
    record = fresh_host.inventory(contract, a.java_home, a.verilator_root)
    with a.output.open('x') as f:
        json.dump(record, f, indent=2)
        f.write('\n')

if __name__ == '__main__':
    main()
