"""Explicit fresh Vector16 host fixtures for the synthetic CI gate, not RTL.

Build each pinned backend once. Export paths only after both original strict
receipts validate; missing or invalid fixtures never become skipped CI tests.
The two R2 environment names refer to the same library and adjacent receipt.
"""
import argparse
import json
import os
from pathlib import Path

from .chunk.vector import (
    LEGACY_BACKEND, FINITE_MUL_UF_BACKEND, build_library, verify_library,
)


VECTOR_ENVIRONMENT = (
    ('GDN_VECTOR16_LIBRARY', LEGACY_BACKEND),
    ('GDN_VECTOR16_FINITE_MUL_UF_LIBRARY', FINITE_MUL_UF_BACKEND),
    ('GDN_VECTOR16_R2_LIBRARY', FINITE_MUL_UF_BACKEND),
)


def build(out):
    out = Path(out).resolve()
    if '\n' in str(out) or '\r' in str(out):
        raise ValueError('single-line fixture directory required for environment export')
    out.mkdir(parents=True, exist_ok=False)
    libraries = {backend: build_library(out, arithmetic_backend=backend)
                 for backend in (LEGACY_BACKEND, FINITE_MUL_UF_BACKEND)}
    # Validate both only after all compilation is complete, before any export.
    for backend, library in libraries.items():
        verify_library(library, arithmetic_backend=backend)
    return {name: str(libraries[backend]) for name, backend in VECTOR_ENVIRONMENT}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    values = build(args.out)
    if os.environ.get('GITHUB_ENV'):
        with open(os.environ['GITHUB_ENV'], 'a') as stream:
            for name, value in values.items():
                stream.write(f'{name}={value}\n')
    print(json.dumps(values, sort_keys=True))


if __name__ == '__main__':
    main()
