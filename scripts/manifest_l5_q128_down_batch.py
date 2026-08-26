#!/usr/bin/env python3
import argparse,hashlib,json
from pathlib import Path
RES=['d696173fd6df668ad6f389ea59b6eb7b894a1a8201ae7ee9a28bfeb341575a7a','b4100b9540a3dffa6c6c18255da937f83c1c33ee4c38992679988691f558d5b2','a1c7c029f0df198b8640b2aa7cb23f478233efe7e9c0d8fb498493b573f9b4d1','cbdc338c214e8cc78930f15592814dd116fe464f4c8d7772fe4d1ee6afff47f6','9b5dc1df99f5c49a8c8b821ca4450eeabb17988d2793ebb0eeecc945b54b4fb1','ce5e13d80ee3b2e00719f436ce3d010ccf4604ee34a1a6a18a93cf3745b63187','faa9915ac0a33707c15818db166d1a571c43babd23de11546ba8ee2a668c26ce','f73b0cde53bce38e164e095c5e889268462dc038d09a2b6d005a886e9bc21e81'];PH='661f4f57181636d84868d986af2fb7c07b7c41cc177a0cda3bba987cd599f6dc'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 a=argparse.ArgumentParser();a.add_argument('--batch',type=int,required=True);a.add_argument('--product',type=Path,required=True);a.add_argument('--residual',type=Path,required=True);a.add_argument('--down',type=Path,required=True);a.add_argument('--final',type=Path,required=True);a.add_argument('--output',type=Path,required=True);x=a.parse_args();
 if sha(x.product)!=PH or sha(x.residual)!=RES[x.batch]:raise SystemExit('Q128_DOWN_HASH_FAIL')
 m={'batch':x.batch,'tokens':[x.batch*16,x.batch*16+15],'steps':430080,'residual_chunks':1536,'product_sha256':PH,'residual_sha256':RES[x.batch],'down_sha256':sha(x.down),'final_sha256':sha(x.final)};x.output.write_text(json.dumps(m,indent=2)+'\n');print(f"L5_Q128_DOWN_MANIFEST_PASS batch={x.batch} final_sha256={m['final_sha256']}")
if __name__=='__main__':main()
