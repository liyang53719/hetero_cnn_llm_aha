"""Narrow source projection for the new false elaboration branch, not RTL equivalence."""
import re

def drop_blocks(s):
 token='if(enablePublic21QkvReduction){'
 while token in s:
  start=s.index(token);p=start+len(token);level=1
  while level:
   if s[p]=='{':level+=1
   elif s[p]=='}':level-=1
   p+=1
  s=s[:start]+s[p:]
 return s

def normalized(s):
 s=re.sub(r'/\*.*?\*/|//[^\n]*','',s,flags=re.S)
 return re.sub(r'\s+','',s)

def project(s,name):
 s=drop_blocks(s)
 s=s.replace('enablePublic21QkvReduction:Boolean=false,','')
 s=re.sub(r'  require\(!enablePublic21QkvReduction.*?\)\n','',s,flags=re.S,count=1) if 'require(!enablePublic21QkvReduction' in s else s
 if name=='QwenOwnerProtocol.scala':
  s=re.sub(r'^.*val public21BackendReset=.*\n','',s,flags=re.M)
  s=re.sub(r'^.*val (qkvRouter|ordinaryJob|ordinaryDone|residentInput)=.*\n','',s,flags=re.M)
  s=re.sub(r'if\(enablePublic21QkvReduction\)Some\(qkvRouter.get.io.(window|tiles|vector|drain)\)else ','',s)
  s=s.replace('residentInput','io.resident').replace('ordinaryJob','io.job').replace('ordinaryDone','io.done')
  s=s.replace(',enableKWindow=enablePublic21QkvReduction,enableDenseDrain=enablePublic21QkvReduction','')
  s=s.replace(',enableBinaryAdd=enablePublic21QkvReduction','')
  s=re.sub(r'^.*val reductionOwns=.*\n','',s,flags=re.M)
  s=s.replace('if(enablePublic21QkvReduction)reductionOwns || (active&&mode===1.U) || dense.window.get.busy || dense.drain.get.busy else ','')
 elif name=='HostBlockTop.scala':
  s=s.replace('enablePublic21QkvReduction=enablePublic21QkvReduction,','')
 elif name=='OverlappedSilu.scala':
  s=s.replace(',enableBinaryAdd:Boolean=false','').replace(',enableBinaryAdd=enableBinaryAdd','')
  s=s.replace('new FfnSiluLoanPort(enableBinaryAdd)','new FfnSiluLoanPort')
  s=s.replace('new SiluOwnerPort(enableTileLoan,enableBinaryAdd)','new SiluOwnerPort(enableTileLoan)')
  s=re.sub(r'^.*require\(!enableBinaryAdd.*\n','',s,flags=re.M)
 return normalized(s)
