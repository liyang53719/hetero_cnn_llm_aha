"""Strict official preparation schedule metadata receipt. No execution acceptance.

The driver supplies a catalog built from pinned jars and a fully closed,
cleanup-verified process log. This parser neither opens files nor runs classes.
"""
import hashlib
import re

ROLES=('PREPARE','COMPILER','AUGMENT','PROBE')
HEX=re.compile(r'[0-9a-f]{64}')
IDENTITY=re.compile(r'PREPARE_SCHEDULE_ID_V1 role=(PREPARE|COMPILER|AUGMENT|PROBE) sha=([0-9a-f]{64}) jar=(FIRRTL|TREADLE|PROBE)')
ITEM=re.compile(r'PREPARE_SCHEDULE_ITEM_V1 i=(0|[1-9][0-9]{0,2}) k=(0|[1-9][0-9]{0,4}) sha=([0-9a-f]{64}) jar=(FIRRTL|TREADLE)')
FINAL=re.compile(r'PREPARE_SCHEDULE_V1 pass=true count=([1-9][0-9]{0,2}) augmentIndex=(0|[1-9][0-9]{0,2}) augmentCount=1 orderSha=([0-9a-f]{64}) selfChecks=4')

def need(condition):
 if not condition:raise ValueError('PREPARE_SCHEDULE_SCHEMA')

def is_sha(value):
 return type(value)is str and HEX.fullmatch(value)is not None

def parse(text,catalog,identities):
 """Validate discovered order, not a presupposed transform sequence.

 catalog: name-SHA -> {class_sha, jar}; ordinals sort the name-SHA keys.
 identities: PREPARE/COMPILER/AUGMENT map to catalog name-SHAs; PROBE maps
 to the separately pinned compiled probe's class-byte SHA.
 """
 need(type(text)is str and 0<len(text)<=32768 and text.isascii() and text.endswith('\n') and '\r'not in text)
 need(type(catalog)is dict and 1<=len(catalog)<=16384)
 for name_sha,entry in catalog.items():
  need(is_sha(name_sha) and type(entry)is dict and set(entry)=={'class_sha','jar'})
  need(is_sha(entry['class_sha']) and entry['jar']in ('FIRRTL','TREADLE') and type(entry['jar'])is str)
 need(type(identities)is dict and set(identities)==set(ROLES))
 need(all(is_sha(identities[role]) for role in ROLES))
 need(all(identities[role]in catalog for role in ROLES[:-1]))
 need(len({identities[role] for role in ROLES[:-1]})==3)
 lines=text.split('\n');need(lines[-1]=='');lines=lines[:-1]
 need(6<=len(lines)<=261)
 verified_identities=[]
 for index,role in enumerate(ROLES):
  match=IDENTITY.fullmatch(lines[index]);need(match is not None and match[1]==role)
  expected={'class_sha':identities['PROBE'],'jar':'PROBE'} if role=='PROBE' else catalog[identities[role]]
  need(match[2]==expected['class_sha'] and match[3]==expected['jar'])
  verified_identities.append(dict(role=role,class_sha=match[2],jar=match[3]))
 final=FINAL.fullmatch(lines[-1]);need(final is not None)
 count=int(final[1]);augment_index=int(final[2]);order_sha=final[3]
 need(1<=count<=256 and 0<=augment_index<count and len(lines)==count+5)
 names=sorted(catalog);rows=[];augment_positions=[]
 for index,line in enumerate(lines[4:-1]):
  match=ITEM.fullmatch(line);need(match is not None and int(match[1])==index)
  ordinal=int(match[2]);need(ordinal<len(names))
  name_sha=names[ordinal];expected=catalog[name_sha]
  need(match[3]==expected['class_sha'] and match[4]==expected['jar'])
  if name_sha==identities['AUGMENT']:augment_positions.append(index)
  rows.append(dict(index=index,catalog_index=ordinal,class_name_sha=name_sha,class_sha=match[3],jar=match[4]))
 need(augment_positions==[augment_index])
 actual=hashlib.sha256(('\n'.join(lines[4:-1])+'\n').encode('ascii')).hexdigest()
 need(actual==order_sha)
 return dict(status='PASS_PREPARE_SCHEDULE_METADATA_ONLY',count=count,augment_index=augment_index,
  augment_count=1,post_augment_count=count-augment_index-1,order_sha=order_sha,self_checks=4,
  identities=verified_identities,rows=rows)

FAILURE=re.compile(r'PREPARE_SCHEDULE_FAILURE_V1 phase=(ARGS|IDENTITY|CATALOG|SCHEDULE|EMIT) code=(UNEXPECTED|ARGS|BYTES|FILE|CLASS|LOCATION|RESOURCE|CATALOG|HASH|SELFTEST|COUNT|AUGMENT|OUTPUT)')

def failure(text):
 """Only fixed failure metadata; this result never permits continuation."""
 need(type(text)is str and 0<len(text)<=128 and text.isascii() and text.endswith('\n') and '\r'not in text)
 need(text.count('\n')==1)
 match=FAILURE.fullmatch(text[:-1]);need(match is not None)
 return dict(status='FAILED_PREPARE_SCHEDULE_METADATA_ONLY',phase=match[1],code=match[2])
