"""Compare fresh emitted simulation SV with independently reviewed c7 source-location directory identity.
No module/port/token can change: all noncomment bytes are preserved exactly.
"""
import argparse,hashlib,json,pathlib
from sv_comment_only_identity import digest
D=pathlib.Path(__file__).parent
EXPECTED='252117aacccad52c2bdf926a2b5180c0effc2f54eb650e98ed1328bad51190d5'
def main():
 a=argparse.ArgumentParser();a.add_argument('--sv',type=pathlib.Path,required=True);a.add_argument('--output',type=pathlib.Path,required=True);v=a.parse_args()
 if hashlib.sha256((D/'sv_comment_only_identity.py').read_bytes()).hexdigest()!='2efe7c98127331f1d0b92c1662065d7a28016359c0983199752b8de6c15d0cb6':raise ValueError('reviewed lexer source')
 if v.output.exists():raise ValueError('fresh receipt')
 with v.sv.open('rb') as f:h=digest(f)
 if h!=EXPECTED:raise ValueError('SV_BYTES_EXCEPT_SOURCEINFO_DIRECTORIES_DRIFT_STOP_AUDIT')
 with v.sv.open('rb') as f:raw=hashlib.file_digest(f,'sha256').hexdigest()
 v.output.write_text(json.dumps({'scope':'PASS_SV_SOURCEINFO_DIRECTORY_IDENTITY_ONLY_NO_NUMERICS','sv_sha256':raw,'source_location_directory_sha256':h},indent=2)+'\n')
if __name__=='__main__':main()
