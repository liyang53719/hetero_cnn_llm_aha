"""Exact dependency projection from original locked metadata, never a runtime import.
Legacy contracts retain the original53 union. Selected contracts bind the precise
profile policy and the union of only its required original runtimes.
"""
import hashlib,importlib.util,pathlib
P=pathlib.Path;D=P(__file__).resolve().parent
_spec=importlib.util.spec_from_file_location('runtime_dependency_policy',D.parent/'profile_policy.py');policy=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(policy)
KEYS=('qwen2','qwen35_08b','qwen35_35b')
SELECTED_ARCHIVES='SELECTED_ORIGINAL_RUNTIME_ARCHIVE_UNION_V1'
SELECTED_INVENTORY='PINNED_EXISTING_SELECTED_RUNTIME_BYTES_V1'
SELECTED_OWNER='SHARED_SELECTED_RUNTIME_OWNER_FRESH_JOB_V1'
SELECTED_REUSE_OWNER='IMPORTED_SELECTED_RUNTIME_OWNER_CLOUD_V1'
SELECTED_BINDING='FRESH_JOB_SELECTED_RUNTIME_INSTALL_BINDING_V1'
SELECTED_RECEIPTS='FRESH_JOB_SELECTED_RUNTIME_RECEIPTS_V1'
SELECTED_PHASE='FRESH_SELECTED_RUNTIME_INSTALL_RESULT_V1'
SELECTED_IMPORT='FRESH_SELECTED_RUNTIME_IMPORT_VALIDATION_V1'
def need(value,message):
 if not value:raise ValueError(message)
def sha(path):
 with P(path).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def selected(b):
 policy.checked(b)
 return policy.is_selected(b)
def require_pins(b):
 policy.require_source_pin(b['pins'])
 need(b['pins'].get(str(D/'runtime_dependencies.py'))==sha(D/'runtime_dependencies.py'),'explicit runtime dependency source pin')
def require_runtime(b,key):
 need(type(key)is str and key in policy.runtimes(b),'selected runtime not permitted by execution policy')
 if selected(b):require_pins(b)
def schema(b,original,chosen):return chosen if selected(b)else original
def archive_scope(b,reuse=False):
 return schema(b,'READ_EXISTING_PINNED_ARCHIVES_NO_INSTALL'if reuse else'ORIGINAL53_ARCHIVE_ONLY_NO_INSTALL','READ_EXISTING_SELECTED_PINNED_ARCHIVES_NO_INSTALL_V1'if reuse else'SELECTED_ORIGINAL_ARCHIVES_ONLY_NO_INSTALL_V1')
def archive_fields(b):
 return dict(schema=SELECTED_ARCHIVES,execution_policy=policy.checked(b))if selected(b)else{}
def check_archive_fields(b,value,reuse=False):
 need(value.get('scope')==archive_scope(b,reuse),'exact original archive validation scope')
 if selected(b):
  need(value.get('schema')==SELECTED_ARCHIVES,'versioned selected archive validation')
  policy.require_same(b,value)
def union(b,locked):
 chosen=selected(b);items,specs,_=locked.artifacts();keys=policy.runtimes(b)if chosen else KEYS
 allitems=[]
 if not chosen:allitems=[*items,*[x for spec in specs.values()for x in [*spec['artifacts'],spec['transformers']]]]
 else:
  for key in keys:allitems.extend(items if key=='qwen2'else[*specs[key]['artifacts'],specs[key]['transformers']])
 result={}
 for item in allitems:
  name=item['filename'];need(type(name)is str and P(name).name==name and name not in ('','.','..'),'single original archive filename')
  need(name not in result or (result[name]['sha256'],result[name]['bytes'])==(item['sha256'],item['bytes']),'consistent original archive union')
  result[name]=item
 if not chosen:need(len(result)==53 and sum(x['bytes']for x in result.values())==305867713,'original53 exact archive union')
 need(bool(result),'nonempty original dependency union')
 return result
def archive_rows(b,rows,locked,checked,check_metadata=True):
 expected=union(b,locked);need(type(rows)is list and len(rows)==len(expected),'exact original dependency archive count');seen=set()
 for row in rows:
  need(type(row)is dict and set(row)=={'path','bytes','sha256'},'exact original archive pin fields')
  path=checked(row);need(path.name in expected and path.name not in seen,'unique original archive');item=expected[path.name]
  need(type(row['bytes'])is int and row['bytes']==item['bytes']and row['sha256']==item['sha256'],'original official archive exact bytes')
  if check_metadata:locked.check_wheel_metadata(item,path)
  seen.add(path.name)
 need(seen==set(expected),'all and only original dependency archives present')
 return rows
