"""Fail-closed physical-provider definition inventory; does not elaborate or execute RTL.
Duplicate module bodies are informational only; preprocessing context may change semantics.
This inventory never authorizes deduplication or linking.
Non-module compiler directives are not silently discarded. This command inventories only.
"""
import argparse, hashlib, json, re
from pathlib import Path

def modules(text):
    # Preserve string/comment positions so declarations inside them cannot be mistaken for RTL.
    masked = re.sub(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"', lambda m: ' '*len(m[0]), text, flags=re.S)
    tokens=list(re.finditer(r'\b(module|endmodule)\b',masked)); out={}; active=None
    for t in tokens:
        if t[1]=='module':
            if active is not None: raise ValueError('nested module declaration')
            n=re.match(r'\s+(?:(?:automatic|static)\s+)?([A-Za-z_][A-Za-z0-9_$]*)\b',masked[t.end():])
            if not n: raise ValueError('unsupported module name/syntax')
            active=(n[1],t.start())
        else:
            if active is None: raise ValueError('unpaired endmodule')
            name,start=active
            if name in out: raise ValueError('duplicate module within one source')
            out[name]=text[start:t.end()];active=None
    if active is not None: raise ValueError('unclosed module')
    if not out: raise ValueError('no module definitions')
    return out

def inventory(paths):
    definitions={};rows=[];duplicates=[]
    for p in paths:
        data=p.read_bytes();text=data.decode()
        # Strip comments but preserve quoted strings for direct DPI declaration detection.
        clean = re.sub(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"', lambda m: m[0] if m[0].startswith(chr(34)) else ' '*len(m[0]), text, flags=re.S)
        if re.search(r'\b(?:import|export)\s+"DPI',clean):raise ValueError('DPI declaration prohibited')
        rows.append({'path':str(p),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
        for name,body in modules(text).items():
            if name in definitions:
                if definitions[name][1]!=body:raise ValueError('different same-name module: '+name)
                duplicates.append({'module':name,'first':definitions[name][0],'second':str(p),'status':'EXACT_BODY_ONLY_CONTEXT_UNVERIFIED_NO_DEDUP'})
            else:definitions[name]=(str(p),body)
    return {'files':rows,'modules':{n:{'path':p,'sha256':hashlib.sha256(b.encode()).hexdigest()} for n,(p,b) in sorted(definitions.items())},'duplicates':duplicates,'status':'DEFINITION_INVENTORY_ONLY_NOT_LINK_OR_NUMERIC_PASS'}
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('files',nargs='+',type=Path);a=ap.parse_args();print(json.dumps(inventory(a.files),indent=2))
