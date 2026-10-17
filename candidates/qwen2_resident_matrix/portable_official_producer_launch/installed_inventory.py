"""Inspect only distribution metadata in the selected fresh interpreter."""
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys


def main():
    if len(sys.argv)!=2: raise ValueError('one fresh inventory path')
    root=Path(sys.prefix).absolute()
    packages=[]
    for distribution in importlib.metadata.distributions():
        location=Path(distribution.locate_file('')).resolve(strict=True)
        packages.append(dict(name=distribution.metadata['Name'],version=distribution.version,
                             inside_venv=location.is_relative_to(root)))
    result=dict(schema=1,python=platform.python_version(),private_venv=sys.prefix!=sys.base_prefix,
                packages=sorted(packages,key=lambda x:x['name'].lower()))
    raw=(json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
    if len(raw)>65536: raise ValueError('inventory size')
    with Path(sys.argv[1]).open('xb') as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())


if __name__=='__main__': main()
