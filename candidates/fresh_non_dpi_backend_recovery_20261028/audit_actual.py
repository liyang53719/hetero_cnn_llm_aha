#!/usr/bin/env python3
from pathlib import Path
import json,hashlib,re,collections,argparse
D=Path(__file__).resolve().parent
a=argparse.ArgumentParser();a.add_argument('--emission-dir',type=Path,required=True);a.add_argument('--original-annotations',type=Path,required=True);a.add_argument('--fma-sv',type=Path,required=True);a.add_argument('--output',type=Path,required=True);A=a.parse_args();P=A.emission_dir
def need(v,m):
 if not v:raise ValueError(m)
def ident(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return {'bytes':p.stat().st_size,'sha256':h.hexdigest()}
expected={'HostBlockTopV4.lo.fir','original-high-reference.json','low-annotations.json','actual_top_ports.tsv','official-bridge-memory-high.fir','official-emission-ast.fir','HostBlockTopV4.sv','high-annotations.json','EMITTER_SCOPE.txt','official-emission-instances.tsv','canonical-low-identity.json','accepted-original-annotations.json'}
need({p.name for p in P.iterdir()}==expected,'exact12artifactinventory')
rows={p.name:ident(p) for p in sorted(P.iterdir())};need(ident(A.original_annotations)=={'bytes':1353384,'sha256':'e40aecae9e15a890acd6eacabd6974d9470434cc83b40c847a0d50096b2bdeee'},'exactoriginalannotations');need(rows==json.loads((D/'ACTUAL_EMISSION_AUDIT.json').read_text())['artifacts'],'exactreviewedartifactidentities');original=json.loads(A.original_annotations.read_text());accepted=json.loads((P/'accepted-original-annotations.json').read_text());high=json.loads((P/'high-annotations.json').read_text());need(original==accepted,'acceptedannotationsexact')
need(len(original)==8985 and sum(x['class']=='firrtl2.transforms.DontTouchAnnotation' for x in original)==8984,'actualannotations')
changes=[(a,b) for a,b in zip(original,high) if a!=b];need(len(high)==len(original) and changes==[({'class':'firrtl2.options.TargetDirAnnotation','directory':'host-diagnostic'},{'class':'firrtl2.options.TargetDirAnnotation','directory':'compiled-host'})],'onlyTargetDirrelocated')
ports=[x.split('\t') for x in (P/'actual_top_ports.tsv').read_text().splitlines()];need(len(ports)==85 and len({x[0] for x in ports})==85,'85uniqueports');need(sum(int(w) for n,d,w in ports if n.startswith('io_launch_bits_'))==844,'launch844');need({n for n,d,w in ports if w=='512'}=={'io_axi_r_bits_data','io_axi_w_bits_data'},'two512AXI')
lines=[x.split('\t') for x in (P/'official-emission-instances.tsv').read_text().splitlines()[1:]];children=collections.defaultdict(list);ext={}
for parent,kind,inst,module,count in lines:
 if kind=='connector':children[parent].append((inst,module,int(count)))
 elif kind=='extmodule':ext[parent]=(module,int(count))
 else:raise ValueError('unexpectedinstancekind')
expanded=[]
def walk(mod,path,anc):
 need(mod not in anc and len(anc)<128,'acyclichierarchy');expanded.append((path,mod))
 for name,m,n in children[mod]:walk(m,path+'.'+name,anc|{mod})
walk('HostBlockTopV4','HostBlockTopV4',set())
externals=collections.Counter(ext[m][0] for p,m in expanded if m in ext);need(externals=={'qwen2_matrix_command_endpoint':8,'tc_clk_gating':8,'idma_backend_rw_axi_flat_wrap':1},'full4096andoriginalDMA')
bank=[(p,m) for p,m in expanded if m.startswith('UnifiedVectorElement32BankV4')];need(len(bank)==1,'oneshared32bank');bank_alus=[(p,m) for p,m in expanded if p.startswith(bank[0][0]+'.') and m.startswith('HeteroFP32Alu')];need(len(bank_alus)==32,'32bankALUs')
ast=(P/'official-emission-ast.fir').read_text();mems=re.findall(r'^\s*mem ([A-Za-z0-9_]+) :',ast,re.M);need(collections.Counter(m for m in mems if m.startswith('sim_storage_') or m=='sim_denseacc_rows')==collections.Counter(['sim_storage_row_'+str(i) for i in range(16)]+['sim_storage_metadata','sim_denseacc_rows']),'exact18storageMemories')
low=json.loads((P/'canonical-low-identity.json').read_text());need(low['sha256']==rows['HostBlockTopV4.lo.fir']['sha256'] and low['bytes']==rows['HostBlockTopV4.lo.fir']['bytes'],'canonicallowidentity')
sv=(P/'HostBlockTopV4.sv').read_text();defs=re.findall(r'^module\s+(\w+)',sv,re.M);need(len(defs)==len(set(defs)) and 'HostBlockTopV4'in defs,'uniquesvmodules');need(not re.search(r'\b(?:import|export)\s+"DPI',sv),'NoDPIfinalHost')
fma=A.fma_sv;fmatext=fma.read_text();fmadefs=re.findall(r'^module\s+(\w+)',fmatext,re.M);need(set(['HeteroBF16FmaPre','HeteroBF16FmaMul','HeteroBF16FmaPost','HeteroBF16FmaRound'])<=set(fmadefs),'fouroriginalstages')
need(sum(m.startswith('BlockScalarFloat') for p,m in expanded)==17 and sum(m.startswith('HeteroFP32Alu') for p,m in expanded)==81,'actualwholeTopscalarandALUcounts')
result={'status':'PASS_READ_ONLY_ACTUAL_EMISSION_AUDIT_NOT_NUMERICAL','artifact_count':12,'artifacts':rows,'annotation_total':len(high),'dont_touch':8984,'annotation_changes':'onlyTargetDir','ports':{'total':85,'inputs':sum(d=='Input' for n,d,w in ports),'outputs':sum(d=='Output' for n,d,w in ports),'launch_bits':844,'axi_data_bits':512},'expanded_hierarchy_instances':len(expanded),'external_bindings':dict(externals),'logical_matrix_macs':4096,'shared_vector_bank_lanes':32,'whole_top_alu_instances':sum(m.startswith('HeteroFP32Alu') for p,m in expanded),'whole_top_scalar_instances':sum(m.startswith('BlockScalarFloat') for p,m in expanded),'memory_representations':18,'total_DefMemory_nodes':len(mems),'sv_modules':len(defs),'fma_library':ident(fma),'fma_modules':fmadefs,'scope':'Simulation-backend emission and structural identity only; physical providers not linked here; no numerical test or final frozen RTL PASS; no utilization measurement.'}
need(not A.output.exists() and not A.output.is_symlink(),'freshoutput');A.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='artifacts'},indent=2))
