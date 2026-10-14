"""Explicit official-profile attention virtual-root preflight, after fixed overlay."""
import hashlib,json,shutil
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
source=BASE/'assembled_current';out=BASE/'dispatch_source'
if out.exists():raise ValueError('fresh dispatch source required')
manifest=json.loads((BASE/'manifest.json').read_bytes())
for p,h in manifest['post_sha256'].items():
 if hashlib.sha256((source/p).read_bytes()).hexdigest()!=h:raise ValueError('frozen overlay drift '+p)
shutil.copytree(source,out)
p='chisel/continuous_prefill/src/main/scala/heteronpu/continuous/HostBlockCommands.scala'
text=(out/p).read_text();before=hashlib.sha256(text.encode()).hexdigest()
def replace(old,new):
 global text
 if text.count(old)!=1:raise ValueError('explicit attention hunk mismatch '+old[:60])
 text=text.replace(old,new)
replace('  val resident=if(enableResidentFfn)Some(new ResidentHostState)else None',
'''  val resident=if(enableResidentFfn)Some(new ResidentHostState)else None
  // Match the explicit software public21 hardening before any Attention issue.
  // Reuse the FFN typed-root scanner and its existing metadata ports/state.
  val scanAttention=if(enableResidentFfn && officialBf16)Some(RegInit(false.B))else None
  val attentionScan=scanAttention.getOrElse(false.B)''')
replace('      if(enableResidentFfn){when(residentAct){resident.get.pending:=true.B;resident.get.scanPc:=0.U;state:=scanFetch}}',
'''      if(enableResidentFfn){
        when(residentAct){resident.get.pending:=true.B;resident.get.scanPc:=0.U;state:=scanFetch;scanAttention.foreach(_:=false.B)}
        if(officialBf16){when(pv){
          resident.get.pending:=false.B;resident.get.scanPc:=0.U;scanAttention.get:=true.B;state:=scanFetch
        }}
      }''')
replace('      val gateUse=(r.scanPc===pc-2.U && r.scanSlot===2.U) || (r.scanPc===pc && r.scanSlot===0.U)\n      val upUse=(r.scanPc===pc-1.U && r.scanSlot===2.U) || (r.scanPc===pc && r.scanSlot===1.U)',
'''      val gateUse=(r.scanPc===pc-2.U && r.scanSlot===2.U) ||
        Mux(attentionScan,r.scanPc===pc-1.U && r.scanSlot===0.U,r.scanPc===pc && r.scanSlot===0.U)
      val upUse=(r.scanPc===pc-1.U && r.scanSlot===2.U) ||
        (r.scanPc===pc && Mux(attentionScan,r.scanSlot===0.U,r.scanSlot===1.U))''')
replace('            when(virtualCount+&2.U>maxCommands.U){fail(Status.Permission.U)}.otherwise{\n              val first=',
'''            // QK/Softmax already reserved these two spans sequentially.
            // FFN reserves its new pair only after this complete typed scan.
            when(attentionScan){state:=issue}
            .elsewhen(virtualCount+&2.U>maxCommands.U){fail(Status.Permission.U)}.otherwise{
              val first=''')
(out/p).write_text(text)
after={name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in manifest['post_sha256']}
changed=[name for name,h in manifest['post_sha256'].items() if after[name]!=h]
if changed!=[p]:raise ValueError('exact one parser target required')
receipt=dict(scope='OFFICIAL_PUBLIC21_ATTENTION_PREFLIGHT_ONLY',base_overlay_manifest=hashlib.sha256((BASE/'manifest.json').read_bytes()).hexdigest(),
 adapter=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),before_sha256=manifest['post_sha256'],post_sha256=after,
 changed_sources=changed,default_off_unchanged=True,arithmetic_executed=False,compiled=False)
(out/'attention_preflight_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(dict(before=before,after=after[p],changed=changed)))
