#!/usr/bin/env python3
import argparse,hashlib,json
from pathlib import Path
PRODUCT={128:'661f4f57181636d84868d986af2fb7c07b7c41cc177a0cda3bba987cd599f6dc',384:'8e2484ecca62c93071ecd7c4f0c3ae9cf0933a6cd652124ba379c9b9b72f0f15'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 a=argparse.ArgumentParser();a.add_argument('--workload',type=int,choices=PRODUCT,default=128);a.add_argument('--batch',type=int,required=True);a.add_argument('--product',type=Path,required=True);a.add_argument('--residual',type=Path,required=True);a.add_argument('--down',type=Path,required=True);a.add_argument('--final',type=Path,required=True);a.add_argument('--output',type=Path,required=True);x=a.parse_args();
 source=json.loads((x.residual.parent/'manifest.json').read_text());expected=source['node_sha256']['residual1']
 if source.get('workload_tokens',128)!=x.workload or source['batch_index']!=x.batch or sha(x.product)!=PRODUCT[x.workload] or sha(x.residual)!=expected:raise SystemExit(f'Q{x.workload}_DOWN_HASH_FAIL')
 m={'workload':x.workload,'batch':x.batch,'tokens':[x.batch*16,x.batch*16+15],'steps':430080,'residual_chunks':1536,'product_sha256':PRODUCT[x.workload],'residual_sha256':expected,'down_sha256':sha(x.down),'final_sha256':sha(x.final)};x.output.write_text(json.dumps(m,indent=2)+'\n');print(f"L5_Q_PREFILL_DOWN_MANIFEST_PASS workload={x.workload} batch={x.batch} final_sha256={m['final_sha256']}")
if __name__=='__main__':main()
