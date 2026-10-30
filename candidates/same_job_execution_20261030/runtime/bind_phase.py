"""Metadata-only owner bind with 64MiB write hard limit; existing inputs may be larger."""
import argparse,hashlib,importlib.util,json,pathlib,resource
P=pathlib.Path
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 a=argparse.ArgumentParser();a.add_argument('--binding',type=P,required=True);a.add_argument('--sha256',required=True);v=a.parse_args()
 if sha(v.binding)!=v.sha256:raise ValueError('independent metadata phase binding')
 b=json.loads(v.binding.read_text());p=P(b['owner_module'])
 if sha(p)!=b['owner_module_sha256']:raise ValueError('owner module drift')
 resource.setrlimit(resource.RLIMIT_FSIZE,(64<<20,64<<20))
 s=importlib.util.spec_from_file_location('fresh_owning_job',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
 m.bind(P(b['owner_binding']),b['owner_binding_sha256'],P(b['receipt_index']),b['receipt_index_sha256'],P(b['output']))
if __name__=='__main__':main()
