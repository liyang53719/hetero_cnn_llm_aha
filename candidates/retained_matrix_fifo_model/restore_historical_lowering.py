from pathlib import Path
import hashlib,sys
P=Path(__file__).resolve().parent
s=(P/'source/MatrixResultFifoMemoryLowering.scala').read_text()
def sha(x):return hashlib.sha256(x.encode()).hexdigest()
a='  private def memoryDeclarations:Seq[Statement]=names.zip(widths).flatMap {case(n,w)=>Seq(\n    DefMemory(NoInfo,n,u(w),BigInt(2),1,0,Seq("r"),Seq("w"),Seq.empty,ReadUnderWrite.Undefined),\n'
b='  private def memoryDeclarations:Seq[Statement]=names.zip(widths).map {case(n,w)=>\n    DefMemory(NoInfo,n,u(w),BigInt(2),1,0,Seq("r"),Seq("w"),Seq.empty,ReadUnderWrite.Undefined) }\n  // Declare storage at its original position, but default ports only after\n  // original head/tail declarations and before the original conditional write.\n  private def memoryDefaults:Seq[Statement]=names.zip(widths).flatMap {case(n,w)=>Seq(\n'
if s.count(b)!=1 or s.count('read+=1;Block(memoryDefaults++reads)')!=1:raise ValueError('exact current source required')
old=s.replace(b,a).replace('read+=1;Block(memoryDefaults++reads)','read+=1;Block(reads)')
if sha(old)!='0e2123911e760826ae5fe3264e2a8a159b8d26f9d16c913267c917ddd8febcdc':raise ValueError('exact0045 hash')
prior=old.replace('3c2de541b70128c5fdc989b65e2013a83a925053fea78ea7483630c163b8db3e','40e2568987ea333eeb99355c613b222312a1806f936c09b7f7db70bb696a02f1')
if sha(prior)!='0838c3b2d6a53fddace81ab12cf9441fd4fd5a217e6f572731389f3cf883d42d':raise ValueError('exact2308 hash')
if len(sys.argv)!=2:raise ValueError('one new output directory argument')
out=Path(sys.argv[1]);out.mkdir(exist_ok=False)
for name,text in [('0045',old),('2308',prior)]:
 d=out/name;d.mkdir();(d/'MatrixResultFifoMemoryLowering.scala').write_text(text)
