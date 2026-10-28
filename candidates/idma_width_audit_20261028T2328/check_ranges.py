import json, hashlib, pathlib, re
root=pathlib.Path('physical_provider_recovery_20261028T2234')
paths=[root/'providers/idma_backend_rw_axi_flat_wrap.sv',root/'artifact/idma_export/idma/src/backend/idma_legalizer_page_splitter.sv',root/'artifact/idma_export/idma/target/rtl/idma_generated.sv',root/'artifact/idma_export/deps/axi_stream/src/axi_stream_cut.sv',root/'artifact/idma_export/deps/axi_stream/src/axi_stream_multicut.sv']
checks=[]
for k in range(6,13):
 count=0; maximum=0
 for a in range(1<<k):
  for n in range(1,(1<<k)-a+1):
   wide=(n+(a%64)-1)>>6
   if not 0<=wide<256: raise RuntimeError((k,a,n,wide))
   maximum=max(maximum,wide);count+=1
 checks.append(dict(page_address_width=k,pairs=count,max_axi_len=maximum))
# Lexical incoming-edge closure, across all recovered source and actual generated Host/FMA.
files=list((root/'artifact/idma_export').rglob('*.sv'))+list((root/'artifact/idma_export').rglob('*.svh'))+list((root/'providers').glob('*.sv'))
files += [pathlib.Path('fresh_non_dpi_emitter_candidate_20261028T2237/actual-host/compiled-host/HostBlockTopV4.sv'),pathlib.Path('physical_frontend_runner_20261028T2241/FreshPhysicalFmaSubset.sv')]
pat=re.compile(r'\baxi_stream_(?:cut|cut_intf|multicut|multicut_intf)\b')
hits={}
for p in files:
 found=[(i,l.strip()) for i,l in enumerate(p.open(),1) if pat.search(l)]
 if found: hits[str(p)]=found
out=dict(scope='FINITE INTEGER RANGE CHECK / LEXICAL SOURCE REACHABILITY ONLY; NOT RTL OR NUMERICAL PASS',offset_width=6,burst_len_default=8,page_width_preclamp=list(range(6,15)),active_page_width=10,checks=checks,hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},stream_cut_name_occurrences=hits,files_scanned=len(files))
pathlib.Path('idma_width_audit_20261028T2328/range_results.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k not in ['stream_cut_name_occurrences','hashes']},indent=2));print('occurrence_files',list(hits)); print(json.dumps(out['hashes'],indent=2))
