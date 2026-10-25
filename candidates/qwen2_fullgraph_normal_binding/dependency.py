"""Exact existing PyYAML package reuse, never site-packages-wide permission."""
import hashlib
import json
from pathlib import Path


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def need(condition,message):
    if not condition:raise ValueError(message)


def check_file(path,pin):
    need(not path.is_symlink() and path.is_file(),'non-regular dependency')
    need(path.stat().st_size==pin['bytes'] and digest(path)==pin['sha256'],'dependency bytes differ: '+path.name)


def manifest(path, expected_sha):
    need(digest(path)==expected_sha,'dependency manifest hash')
    data=json.loads(Path(path).read_text())
    need(data['schema']==1 and data['package']=='PyYAML' and data['version']=='6.0.3','exact reviewed package')
    need(len(data['files'])==18 and sum(p.endswith('.py') for p in data['files'])==17,'complete 18-file package')
    need('yaml/_yaml.cpython-312-x86_64-linux-gnu.so' in data['files'] and data['normal_cyaml_required'] is True,'normal cyaml is required')
    need(data['unrestricted_site_packages_allowed'] is False,'no broad site-packages permission')
    need(all(Path(p).parts[0]=='yaml' and len(Path(p).parts)==2 and not Path(p).is_absolute() for p in data['files']),'dependency relative path')
    return data


def verify_copy(root, spec):
    root=Path(root).resolve(strict=True)
    actual={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
    need(actual==set(spec['files']),'dedicated yaml root has missing or extra files')
    need(all(not p.is_symlink() for p in root.rglob('*')),'dependency symlink forbidden')
    for relative,pin in spec['files'].items():check_file(root/relative,pin)
    return {str(root/relative):pin for relative,pin in spec['files'].items()}


def copy_existing(original_site_root, destination, spec):
    import base64
    import csv
    source=Path(original_site_root).resolve(strict=True);dest=Path(destination).resolve()
    need(not dest.exists(),'fresh dependency destination required')
    for relative,pin in spec['metadata_pins'].items():check_file(source/relative,pin)
    originals={str(p.relative_to(source)) for p in (source/'yaml').iterdir() if p.is_file() and (p.suffix=='.py' or '.so' in p.name)}
    need(originals==set(spec['files']),'installed yaml package extent differs')
    rows={row[0]:row[1:] for row in csv.reader((source/'pyyaml-6.0.3.dist-info/RECORD').read_text().splitlines())}
    for relative,pin in spec['files'].items():
        check_file(source/relative,pin)
        expected='sha256='+base64.urlsafe_b64encode(bytes.fromhex(pin['sha256'])).decode().rstrip('=')
        need(rows.get(relative)==[expected,str(pin['bytes'])],'installed RECORD differs: '+relative)
    dest.mkdir();(dest/'yaml').mkdir()
    for relative in spec['files']:
        with (dest/relative).open('xb') as out:out.write((source/relative).read_bytes())
    return verify_copy(dest,spec)
