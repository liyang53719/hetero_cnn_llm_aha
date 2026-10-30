"""Original full128 reference in same outer-owned PID; lifecycle only."""
import argparse,hashlib,json,pathlib,resource,runpy,sys
P=pathlib.Path
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 a=argparse.ArgumentParser();a.add_argument('--binding',type=P,required=True);a.add_argument('--sha256',required=True);v=a.parse_args()
 if sha(v.binding)!=v.sha256:raise ValueError('independently admitted reference invocation')
 b=json.loads(v.binding.read_text());argv=b['argv'];p=P(argv[0])
 if sha(p)!=b['source_sha256']or not p.is_absolute():raise ValueError('original reference source identity')
 resource.setrlimit(resource.RLIMIT_FSIZE,(128<<20,128<<20))
 sys.path.insert(0,str(p.parent));sys.argv=argv;runpy.run_path(str(p),run_name='__main__')
if __name__=='__main__':main()
