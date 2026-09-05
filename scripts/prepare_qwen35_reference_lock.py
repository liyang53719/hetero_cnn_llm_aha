#!/usr/bin/env python3
"""Pin public reference metadata; never call metadata availability hardware PASS."""
import hashlib,json
from pathlib import Path
from huggingface_hub import HfApi,hf_hub_download
ROOT=Path(__file__).resolve().parents[1]
MODEL='Qwen/Qwen3.5-35B-A3B'
REV='62704185bd97ad488cfc404e7caea797396b74dc'
def main():
    profile=json.loads((ROOT/'config/model_profiles/qwen3_5_35b_a3b.json').read_text())
    assert profile['model_id']==MODEL and profile['revision']==REV
    info=HfApi().model_info(MODEL,revision=REV,files_metadata=True);assert info.sha==REV
    dest=ROOT/'work/models/qwen3_5_35b_a3b_62704185'
    names={x.rfilename for x in info.siblings};metadata={}
    for name in ['config.json','model.safetensors.index.json','tokenizer_config.json']:
        assert name in names
        path=Path(hf_hub_download(MODEL,name,revision=REV,local_dir=dest))
        metadata[name]={'path':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    index=json.loads((dest/'model.safetensors.index.json').read_text())
    weights=[dict(file=x.rfilename,bytes=x.size) for x in info.siblings if x.rfilename.endswith('.safetensors')]
    assert set(index['weight_map'].values())=={w['file'] for w in weights}
    report=dict(status='PASS_REFERENCE_METADATA_ONLY',model_id=MODEL,revision=REV,
                private=info.private,gated=info.gated,metadata=metadata,weight_shards=weights,
                total_weight_bytes=sum(w['bytes'] for w in weights),tensor_names=len(index['weight_map']),
                weights_downloaded=False,numerical_rtl_pass=False,
                next='Stream/load bounded layers and experts; full BF16 checkpoint exceeds30GiB cap, do not load entire model')
    (ROOT/'reports/execution/QWEN35_REFERENCE_LOCK.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['status','revision','total_weight_bytes','tensor_names']}))
if __name__=='__main__':main()
