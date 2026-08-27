#!/usr/bin/env python3
"""Structural-only SystemVerilog source check; never reported as elaboration."""
from __future__ import annotations
import json
import re
from pathlib import Path

errors=[]
modules=[]
for path in Path('rtl').rglob('*.sv'):
    source=path.read_text()
    stripped=re.sub(r'/\*.*?\*/','',source,flags=re.S)
    stripped=re.sub(r'//.*','',stripped)
    names=re.findall(r'\bmodule\s+([A-Za-z_][A-Za-z0-9_$]*)',stripped)
    modules.extend(names)
    if len(names)!=len(re.findall(r'\bendmodule\b',stripped)):
        errors.append({'path':str(path),'error':'module_endmodule_count'})
    stack=[]
    pairs={')':'(',']':'[','}':'{'}
    for char in stripped:
        if char in '([{':stack.append(char)
        elif char in pairs:
            if not stack or stack.pop()!=pairs[char]:
                errors.append({'path':str(path),'error':'delimiter_mismatch'})
                break
    if stack:errors.append({'path':str(path),'error':'unclosed_delimiter'})
result={'schema_version':4,'status':'PASS' if not errors else 'FAIL','module_count':len(modules),'modules':modules,'errors':errors,'evidence_class':'source_structural_not_compiler'}
Path('reports/rtl_source_check_v4.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print(json.dumps(result,indent=2,sort_keys=True))
raise SystemExit(bool(errors))
