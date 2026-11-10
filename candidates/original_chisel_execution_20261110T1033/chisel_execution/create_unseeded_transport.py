from pathlib import Path
import re,json,hashlib
R=Path(__file__).resolve().parent;W=R.parents[1];O=R/'unseeded_v2';O.mkdir(exist_ok=True)
S=W/'round_20261110T0133/recovery/sources/hetero_cloud_recovery_20261107T2134/candidates/chisel_hybrid_host_20261106/scala'
header=W/'round_20261110T0933/host/obj_hier/Vqwen2_matrix_command_endpoint/Vqwen2_matrix_command_endpoint.h'
ports=[dict(direction=d,name=n,width=int(h)-int(l)+1) for d,n,h,l in re.findall(r'VL_(IN|OUT)(?:8|16|64|W)?\(&([A-Za-z0-9_]+),(\d+),(\d+)(?:,\d+)?\);',header.read_text())]
if len(ports)!=22 or any('seed' in p['name'] for p in ports):raise ValueError('not exact unseeded interface')
layout=(S/'MatrixNativeLayout.scala').read_text();layout='\n'.join(l for l in layout.splitlines() if not re.search(r'Field\("(?:seed_|arithmetic_)',l))+'\n';layout=layout.replace('inputWords=63; val outputWords=533','inputWords=37; val outputWords=521').replace('abiVersion=65536','abiVersion=131072')
fields=[(n,int(w)) for n,w in re.findall(r'Field\("([^"]+)",(\d+),\d+\)',layout)]
if dict(fields+[('clk_i',1)])!={p['name']:p['width'] for p in ports}:raise ValueError('layout/header mismatch')
contract=hashlib.sha256(json.dumps(ports,sort_keys=True,separators=(',',':')).encode()).hexdigest();layout=re.sub(r'contractSha256="[a-f0-9]+"','contractSha256="'+contract+'"',layout)
renames={'AllNativeRetainedModelFactory':'UnseededNativeRetainedModelFactoryV2','MatrixNativeLayout':'UnseededMatrixNativeLayoutV2','MatrixNativeBlackBox':'UnseededMatrixNativeBlackBoxV2','RetainedMatrixNativeLeaf':'UnseededRetainedMatrixNativeLeafV2','MatrixLeafNative':'UnseededMatrixLeafNativeV2'}
source={'MatrixNativeLayout.scala':layout}
for n in ['RetainedMatrixNativeLeaf.scala','MatrixNativeBlackBox.scala','AllNativeRetainedModelFactory.scala']:
 s=(S/n).read_text()
 s=s.replace('require(params==Seq(IntParam("ENABLE_ACCUMULATOR_SEED",BigInt(1)))','require(params.isEmpty')
 s=s.replace('val params=if(e.defname==matrixName)Seq(IntParam("ENABLE_ACCUMULATOR_SEED",BigInt(1)))else Seq.empty','val params=Seq.empty')
 s=s.replace('private val seedBlock=Seq("seed_begin_valid_i","seed_beat_valid_i","seed_commit_valid_i","seed_abort_i")','private val seedBlock=Seq.empty[String]')
 s='\n'.join(l for l in s.splitlines() if 'case "seed_' not in l)+'\n'
 s=s.replace('\\"matrixSeed\\":1','\\"matrixSeed\\":0').replace('hybrid Chisel Host + native original RTL leaves','hybrid Chisel Host + native unseeded RTL leaves ABI v2')
 source[n]=s
for n,s in source.items():
 for a,b in renames.items():s=s.replace(a,b)
 s=s.replace('retained_matrix_','retained_matrix_unseeded_v2_')
 (O/(renames.get(n[:-6],n[:-6])+'.scala')).write_text(s)
cpp=(R/'matrix_icg/retained_matrix_leaf.cpp').read_text();lines=[]
for l in cpp.splitlines():
 if 'seed_' in l or 'arithmetic_' in l:continue
 m=re.search(r'words\[(\d+)\]',l)
 if m and (("return -1" in l and int(m[1])>=37) or ("return -4" in l and int(m[1])>=521)):continue
 lines.append(l)
cpp='\n'.join(lines)+'\n';cpp=cpp.replace('"retained_matrix_leaf.h"','"unseeded_matrix_v2.h"').replace('retained_matrix_','retained_matrix_unseeded_v2_')
cpp+='extern "C" int retained_matrix_unseeded_v2_seed_request(void*,const uint32_t*,uint32_t){return -7;} // unsupported, even zero request\n'
(O/'unseeded_matrix_v2.cpp').write_text(cpp)
h='''#pragma once
#include <stdint.h>
#define RETAINED_MATRIX_ABI_VERSION 131072u
#define RETAINED_MATRIX_INPUT_WORDS 37u
#define RETAINED_MATRIX_OUTPUT_WORDS 521u
#define RETAINED_MATRIX_CONTRACT_SHA256 "'''+contract+'''"
#ifdef __cplusplus
extern "C" {
#endif
uint32_t retained_matrix_unseeded_v2_abi_version();
const char* retained_matrix_unseeded_v2_contract_sha256();
void* retained_matrix_unseeded_v2_create();
int retained_matrix_unseeded_v2_destroy(void*);
int retained_matrix_unseeded_v2_drive(void*,const uint32_t*,uint32_t);
int retained_matrix_unseeded_v2_eval(void*);
int retained_matrix_unseeded_v2_clock(void*,uint32_t);
int retained_matrix_unseeded_v2_read(void*,uint32_t*,uint32_t);
int retained_matrix_unseeded_v2_edge_counts(void*,uint64_t*,uint64_t*);
int retained_matrix_unseeded_v2_seed_request(void*,const uint32_t*,uint32_t);
#ifdef __cplusplus
}
#endif
''';(O/'unseeded_matrix_v2.h').write_text(h)
(O/'CONTRACT.json').write_text(json.dumps({'ports':ports,'port_count':22,'contract_sha256':contract,'abi':131072,'input_words':37,'output_words':521,'seed_request':'always error -7','numeric_oracle':False,'hardware_qualification':False},indent=2))
print('generated versioned unseeded transport; exact22 header ports')
