"""Rebuild exact single-key declaration metadata from the pinned published baseline.
No actual FIR/SV or model execution; outputs are declaration expectations only.
"""
from pathlib import Path
import argparse,copy,hashlib,importlib.util,json
ROOT=Path(__file__).resolve().parents[2]
BASELINE=ROOT.parent/'unified_shared_resource_fabric'
OLD_SHA='7ec0344b8ddfe1a2e31203b30001285dbc7d031f7e9948f0cb3d5a3ffce71813'
NEW_SHA='c434688a68bab15900a0f109fd1b75566c4f095c7daa8ef404d02211a8adc31a'
HELPER_SHA='466c2826b1c63e40db17ab931cc87aa8399644f56d456ffb955fa09df51a9e97'
def need(ok,why):
    if not ok:raise ValueError(why)
def load_baseline(root=BASELINE):
    p=Path(root)/'checks/sv/reconstruct_expectation.py'
    need(not p.is_symlink() and p.is_file() and p.stat().st_size<10000,'baseline helper file')
    need(hashlib.sha256(p.read_bytes()).hexdigest()==HELPER_SHA,'baseline helper identity')
    spec=importlib.util.spec_from_file_location('fixed_public_declaration_reconstructor',p)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m

def transform(old):
    need(isinstance(old,bytes) and len(old)==1868089 and hashlib.sha256(old).hexdigest()==OLD_SHA,'exact baseline expectation')
    need(old.count(b'"integer":')==1,'unique exact key')
    new=old.replace(b'"integer":',b'"integer_0":',1)
    a=json.loads(old);b=json.loads(new);inverse=copy.deepcopy(b)
    need(len(b['scalar_direct_families'])==4 and b['scalar_direct_families']['integer_0']=='INToRecFN_i32_e8_s24','exact four scalar children')
    inverse['scalar_direct_families']['integer']=inverse['scalar_direct_families'].pop('integer_0')
    need(inverse==a,'no other metadata change')
    need(len(new)==1868091 and hashlib.sha256(new).hexdigest()==NEW_SHA,'exact successor expectation')
    need(len(b['selected_module_ports']['UnifiedSharedResourceTop'])==4599 and sum(len(v)for v in b['selected_module_ports'].values())==9308,'strict unchanged seven-module ABI')
    return new

def build(root=BASELINE):return transform(load_baseline(root).build())
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--baseline',type=Path,default=BASELINE);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    m=load_baseline(a.baseline);new=transform(m.build());m.write_new(a.output,new)
    print(json.dumps({'bytes':len(new),'sha256':hashlib.sha256(new).hexdigest(),'scope':'declaration metadata, not actual RTL or numerical acceptance'}))
