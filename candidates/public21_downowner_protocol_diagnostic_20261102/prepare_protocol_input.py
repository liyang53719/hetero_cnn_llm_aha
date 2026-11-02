"""Lossless field selection of protocol metadata, never tensor data or weights."""
import argparse,hashlib,json
from pathlib import Path
SCOPE='EXACT_SELECTED_PROTOCOL_METADATA_NOT_TENSOR_OR_NUMERICAL_EVIDENCE'
def sha(x):return hashlib.sha256(x).hexdigest()
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':')).encode()
def project(raw,expected):
    if sha(raw)!=expected:raise ValueError('independent original manifest SHA mismatch')
    d=json.loads(raw);paths=['/tokens','/shape/H','/commands']+[f'/tensors/{n}/{f}' for n in ('n0','wq','q') for f in ('dims','address')]
    def get(p):
        v=d
        for k in p[1:].split('/'):v=v[k]
        return v
    fields={p:get(p) for p in paths}
    result={'tokens':fields['/tokens'],'shape':{'H':fields['/shape/H']},'commands':fields['/commands'],'tensors':{n:{f:fields[f'/tensors/{n}/{f}'] for f in ('dims','address')} for n in ('n0','wq','q')}}
    if result['tokens']!=128 or result['shape']['H']!=1536 or result['commands']!=21:raise ValueError('actual recipe mismatch')
    for n,t in result['tensors'].items():
        if t['dims']!=[1536 if n=='wq' else 128,1536] or type(t['address']) is not int or not 0<=t['address']<2**53:raise ValueError('tensor descriptor')
    result['protocol_metadata_provenance']={'schema':'P0_EXACT_PROTOCOL_FIELD_PROJECTION_V1','scope':SCOPE,'source_manifest_sha256':expected,'source_manifest_bytes':len(raw),'selected_fields':fields,'selected_fields_sha256':sha(canonical(fields))}
    return result

def verify(d,expected):
    if set(d)!={'tokens','shape','commands','tensors','protocol_metadata_provenance'}:raise ValueError('projection exact keys')
    p=d['protocol_metadata_provenance']
    if set(p)!={'schema','scope','source_manifest_sha256','source_manifest_bytes','selected_fields','selected_fields_sha256'} or p['schema']!='P0_EXACT_PROTOCOL_FIELD_PROJECTION_V1' or p['scope']!=SCOPE or p['source_manifest_sha256']!=expected:raise ValueError('projection source binding')
    fields=p['selected_fields']
    if sha(canonical(fields))!=p['selected_fields_sha256']:raise ValueError('field digest')
    want=['/tokens','/shape/H','/commands']+[f'/tensors/{n}/{f}' for n in ('n0','wq','q') for f in ('dims','address')]
    if set(fields)!=set(want) or type(p['source_manifest_bytes']) is not int or p['source_manifest_bytes']<=0:raise ValueError('field closure')
    if set(d['shape'])!={'H'} or set(d['tensors'])!={'n0','wq','q'} or any(set(t)!={'dims','address'} for t in d['tensors'].values()):raise ValueError('no extra data')
    for path,value in fields.items():
        v=d
        for k in path[1:].split('/'):v=v[k]
        if v!=value:raise ValueError('field value drift')
    # Source-bound bytes must come from reviewed project() output + independently
    # pinned projection SHA; this verifier cannot reconstruct absent original bytes.
    return True

def main():
    a=argparse.ArgumentParser();a.add_argument('--manifest',type=Path,required=True);a.add_argument('--source-sha256',required=True);a.add_argument('--output',type=Path,required=True);n=a.parse_args()
    d=project(n.manifest.read_bytes(),n.source_sha256);verify(d,n.source_sha256)
    with n.output.open('x') as f:json.dump(d,f,indent=2);f.write('\n')
if __name__=='__main__':main()
