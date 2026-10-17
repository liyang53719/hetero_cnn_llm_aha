import re
from check_sv import need
def ports(text,name):
 text=re.sub(r'/\*.*?\*/|//[^\n]*','',text,flags=re.S)
 matches=list(re.finditer(r'\bmodule\s+'+name+r'\s*\((.*?)\)\s*;',text,re.S));need(len(matches)==1,'one root module '+name)
 result={};direction=None;width=None
 for part in matches[0][1].split(','):
  part=part.strip();m=re.fullmatch(r'(?:(input|output)\s+)?(?:(?:wire|logic)\s+)?(?:\[(\d+)\s*:\s*(\d+)\]\s*)?(\w+)',part)
  need(m is not None,'unknown port syntax '+part)
  if m[1]:direction=m[1];width=1
  if m[2]:need(int(m[3])==0,'nonzero low bit');width=int(m[2])+1
  need(direction is not None and width is not None and m[4] not in result,'duplicate/unknown direction')
  result[m[4]]=[direction,width]
 return result

