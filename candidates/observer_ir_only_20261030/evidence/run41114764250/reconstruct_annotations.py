"""Reconstruct annotation TEXT from pinned local inputs, never execution/PASS.
No download, model, hardware execution, or upload. The historical partial input
is used only as text; this run's independent raw+ordered hashes validate it.
"""
import argparse,hashlib,json,pathlib
PINS={
 'p0':'cf376f327b3203ff0ba03e3392fe0165027d2959c0a582c992249733372f0b09',
 'v1':'8469b2a821f8df3c5c971cd5b9ecb2f531c8334ae945d52fd2f52c8f5429bdab',
 'r2_source':'7c4358e766fca3101657e1702c8fdb2ee579a589eea768fcf1f2eed20412334f',
 'old_raw':'e40aecae9e15a890acd6eacabd6974d9470434cc83b40c847a0d50096b2bdeee',
 'old_ordered':'084025556b70d6a0c7cf992667c40d899b0a897da0fb311c8ec2b253f5d3ca0f',
 'r2_raw':'ee6f1eb80ecf990a89e5c3457a14be74fb5e9ac5e0fa4789404e2d15ddc84dc9',
 'r2_ordered':'8dd84536415d0f97aad603d1e0b9fbdadf8cae58a04d4ae5328105c9a844af39'}
def need(x,m):
 if not x:raise ValueError(m)
def sha(b):return hashlib.sha256(b).hexdigest()
def serial(x):return json.dumps(x,indent=2,separators=(',',':'),ensure_ascii=False).encode()
def read(p,key,cap=4<<20):
 need(p.is_file() and not p.is_symlink() and 0<p.stat().st_size<=cap,'bounded regular input')
 b=p.read_bytes();need(sha(b)==PINS[key],'pinned input '+key);return b
def reconstruct(p0raw,v1raw,source):
 need(sha(p0raw)==PINS['p0'] and sha(v1raw)==PINS['v1'] and sha(source)==PINS['r2_source'],'exact input pins')
 p0=json.loads(p0raw);v1=json.loads(v1raw);need(serial(p0)==p0raw and serial(v1)==v1raw,'exact original JSON serialization')
 prefix='~HostBlockTopV4|HostBlockTopV4>io.'
 def observed(a,name):return a.get('class')=='firrtl2.transforms.DontTouchAnnotation' and a.get('target','').startswith(prefix+name+'.')
 old=[a for a in p0 if not observed(a,'residentObservation')]
 need(len(p0)==9012 and len(old)==8985 and sha(serial(old))==PINS['old_raw'],'completed P0 strip27 restores old bytes')
 def keep(xs):return [a for a in xs if a.get('class')!='firrtl2.options.TargetDirAnnotation']
 need([a for a in old if a.get('class')=='firrtl2.options.TargetDirAnnotation']==[{'class':'firrtl2.options.TargetDirAnnotation','directory':'host-diagnostic'}],'only known TargetDir')
 need(sha(serial(keep(old)))==PINS['old_ordered'],'old ordered annotations preserved')
 need(serial([a for a in v1 if not observed(a,'rawScoreObservation')])==p0raw,'partial V1 text only restores completed P0')
 indices=[i for i,a in enumerate(v1) if observed(a,'rawScoreObservation')]
 need(len(indices)==7 and indices==list(range(indices[0],indices[0]+7)),'contiguous original7 targets')
 suffix=('bits.score','bits.expert','bits.token','bits.profile','bits.ownerSequence','bits.transactionId','valid')
 need([v1[i]['target'] for i in indices]==[prefix+'rawScoreObservation.'+s for s in suffix],'original target order')
 need('val kind=Bool();val rank=UInt(32.W);val last=Bool()' in source.decode(),'exact three appended source fields')
 added=[{'class':'firrtl2.transforms.DontTouchAnnotation','target':prefix+'rawScoreObservation.bits.'+n} for n in ('last','rank','kind')]
 r2=v1[:indices[0]]+added+v1[indices[0]:];raw=serial(r2);ordered=serial(keep(r2))
 need(len(r2)==9022 and len(raw)==1358737 and sha(raw)==PINS['r2_raw'] and sha(ordered)==PINS['r2_ordered'],'actual run41114764250 raw+ordered identity')
 summary=dict(scope='ANNOTATION_TEXT_RECONSTRUCTION_MATCHES_ACTUAL_RUN41114764250_HASHES',raw_bytes=len(raw),raw_sha256=sha(raw),ordered_sha256=sha(ordered),annotation_count=len(r2),dont_touch_count=len(keep(r2)),target_dir_count=len(r2)-len(keep(r2)),original_annotations_relative_order_preserved=True,added_top_observation_targets=37,prior_partial_execution_status_inherited=False,execution_or_numerical_acceptance=False)
 return raw,summary
def main():
 p=argparse.ArgumentParser()
 for name in ('p0-annotations','v1-annotations','r2-source','summary-output'):p.add_argument('--'+name,type=pathlib.Path,required=True)
 p.add_argument('--write-reconstructed-annotations',type=pathlib.Path)
 a=p.parse_args();raw,summary=reconstruct(read(a.p0_annotations,'p0'),read(a.v1_annotations,'v1'),read(a.r2_source,'r2_source'))
 if a.write_reconstructed_annotations:
  with a.write_reconstructed_annotations.open('xb') as f:f.write(raw)
 with a.summary_output.open('x') as f:json.dump(summary,f,indent=2);f.write('\n')
 print(json.dumps(summary))
if __name__=='__main__':main()
