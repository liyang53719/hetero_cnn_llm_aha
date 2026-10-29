"""Byte-preserving six-module FMA selection after exact shared-module comparison."""
from pathlib import Path
import argparse,hashlib,json,re
SELECT=['MulAddRecFNToRaw_preMul_e8_s24','HeteroBF16FmaPre','HeteroBF16FmaMul','MulAddRecFNToRaw_postMul_e8_s24','HeteroBF16FmaPost','HeteroBF16FmaRound']
SHARED=['RoundAnyRawFNToRecFN_ie8_is26_oe8_os24','RoundRawFNToRecFN_e8_s24']
def need(ok,msg):
 if not ok:raise ValueError(msg)
def digest(b):return hashlib.sha256(b).hexdigest()
def modules(b):
 text=b.decode();result={};cursor=0
 for match in re.finditer(r'^module\s+(\w+)\b.*?^endmodule[^\n]*\n?',text,re.M|re.S):
  need(not text[cursor:match.start()].strip(),'external text/directives');name=match[1];need(name not in result,'duplicate module '+name);result[name]=match[0].encode();cursor=match.end()
 need(not text[cursor:].strip(),'trailing external text');need(result,'empty modules');return result

def run(host,hh,fma,fh,out):
 hb=host.read_bytes();fb=fma.read_bytes();need(digest(hb)==hh and digest(fb)==fh,'actual input drift');hm=modules(hb);fm=modules(fb)
 need(set(fm)==set(SELECT+SHARED+['PhysicalFmaStageLibrary']),'FMA exact nine-module set')
 for n in SHARED:need(n in hm and hm[n]==fm[n],'shared module bytes differ '+n)
 need(not any(n in hm for n in SELECT),'FMA selected name collision')
 for n in fm:need('`' not in fm[n].decode(),'FMA macro dependency '+n)
 need(not out.exists(),'fresh subset output');b=b''.join(fm[n] for n in SELECT);out.write_bytes(b)
 report={'status':'EXACT_SUBSET_BYTES_ONLY_NOT_ELABORATION','host_sha256':hh,'fma_sha256':fh,'selected_modules':SELECT,'shared_identical':{n:digest(fm[n]) for n in SHARED},'excluded_unused_carrier':'PhysicalFmaStageLibrary','subset_bytes':len(b),'subset_sha256':digest(b),'host_module_count':len(hm),'fma_module_count':len(fm),'out':str(out)}
 out.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n');return report
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--host',type=Path,required=True);p.add_argument('--host-sha256',required=True);p.add_argument('--fma',type=Path,required=True);p.add_argument('--fma-sha256',required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();print(json.dumps(run(a.host,a.host_sha256,a.fma,a.fma_sha256,a.out),indent=2))
