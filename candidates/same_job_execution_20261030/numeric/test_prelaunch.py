import ast,copy,json,os,pathlib,signal,tempfile,types,unittest,hashlib
from unittest.mock import patch
P=pathlib.Path;D=P(os.environ.get('FIRST_FAULT_LEGACY_TEST_SOURCE',str(P(__file__).resolve().parent.parent))).resolve()/'numeric'
source=ast.parse((D/'numeric_tail.py').read_text())
selected=[n for n in source.body if isinstance(n,ast.FunctionDef)and n.name in ('sha','save','complete','prelaunch_rejection','require_cleanup')or isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id.startswith('PRELAUNCH_')for t in n.targets)]
ns=dict(P=P,json=json,hashlib=hashlib,signal=signal)
exec(compile(ast.Module(body=selected,type_ignores=[]),'numeric_tail.py','exec'),ns)


# Exact V3 fragments, reversed before unchanged full-prefill and older inverses.

# Fixed finite-log source delta, layered before unchanged V3/V2/historical proof.

# Exact aggregate-cap layer; every prior inverse and baseline stays unchanged.
REVIEWED_AGGREGATE_CAP_INVERSE = {'numeric/numeric_tail.py': [('7a4fa6bc7ed201898f0542368513af45ce6c55be8789e059dbe6a7932f559ddb',
                              'if log_disk_bytes:\n'
                              "    caps['tree_bytes'] += log_disk_bytes\n"
                              'if log_disk_bytes or finite_tree:\n'
                              "    caps['min_free_disk_bytes'] = 8 << 30",
                              '64a77e96dd6f114af7d9113367a67d2a7497513c6d75bacb48b29700e4264942',
                              'if log_disk_bytes:\n'
                              "    caps['tree_bytes'] += log_disk_bytes\n"
                              "    caps['min_free_disk_bytes'] = 8 << 30"),
                             ('0925e3f86e921d6dfdcf5797ff570a61c0a17282aaf8e2adec65f6643181f6aa',
                              "finite_tree = admission.get('budget_version') == 3 and "
                              "'aggregate_tree_cap_bytes' in b\n"
                              'if finite_tree:\n'
                              "    body['preserve_free_8gib'] = True",
                              '3543b4693a36a1098850b8bc928887694ed59a6deb7d3dfd0339de01f55a77b6',
                              ''),
                             ('b141b3a35f0b24e143da30aaf04212d80ee814b1f569a63ec96bb7e4fd32a105',
                              "if admission.get('budget_version') == 3 and 'aggregate_tree_cap_bytes' in b:\n"
                              "    need(cloud is not None and type(b['tree_cap']) is int and (0 < "
                              "b['tree_cap'] <= live_budget.TREE_CAP), 'reviewed ordinary FULL finite "
                              "aggregate cap')\n"
                              "elif b.get('reference_data_reuse') is None:\n"
                              "    need(b['tree_cap'] == live_budget.TREE_CAP, 'unchanged aggregate tree "
                              "cap')\n"
                              'else:\n'
                              "    need(cloud is not None and b['execution_mode'] in (execution_mode.STAGE, "
                              "execution_mode.FIRST_FAULT) and (b['tree_cap'] == 12037043872), 'exact "
                              "reference-data-only tree reduction')",
                              '0b5595805095f439f3182779c2f7b7c120b57c7c9fe0b555303e092e306588bc',
                              "if b.get('reference_data_reuse') is None:\n"
                              "    need(b['tree_cap'] == live_budget.TREE_CAP, 'unchanged aggregate tree "
                              "cap')\n"
                              'else:\n'
                              "    need(cloud is not None and b['execution_mode'] in (execution_mode.STAGE, "
                              "execution_mode.FIRST_FAULT) and (b['tree_cap'] == 12037043872), 'exact "
                              "reference-data-only tree reduction')")]}
PRE_AGGREGATE_AST_SHA256 = {'numeric/numeric_tail.py': 'a275e8014536c3bf50b0df6074775ca72ae24f3b90901bbb8aa379a6c5feafe8'}

def undo_reviewed_aggregate_cap_delta(test,tree,relative):
 # Only exact approved aggregate-cap fragments, in reverse source order, before
 # finite-log/V3/V2/history and before their mutation or duplicate fixtures.
 import copy
 tree=copy.deepcopy(tree)
 for digest,new_text,old_digest,old_text in REVIEWED_AGGREGATE_CAP_INVERSE.get(relative,()):
  want=ast.parse(new_text).body;replacement=ast.parse(old_text).body
  fingerprint=lambda body:hashlib.sha256(ast.dump(ast.Module(body=body,type_ignores=[]),include_attributes=False).encode()).hexdigest()
  test.assertEqual(fingerprint(want),digest,'fixed approved aggregate-cap fragment')
  test.assertEqual(fingerprint(replacement),old_digest,'fixed pre-aggregate replacement')
  want_dump=[ast.dump(n,include_attributes=False)for n in want];matches=[]
  def visit(node):
   for field,value in ast.iter_fields(node):
    if isinstance(value,list):
     for i in range(len(value)-len(want)+1):
      if all(isinstance(n,ast.AST)for n in value[i:i+len(want)])and [ast.dump(n,include_attributes=False)for n in value[i:i+len(want)]]==want_dump:matches.append((value,i))
     for item in value:
      if isinstance(item,ast.AST):visit(item)
    elif isinstance(value,ast.AST):visit(value)
  visit(tree)
  test.assertEqual(len(matches),1,'one exact aggregate-cap fragment: '+digest)
  container,index=matches[0];container[index:index+len(want)]=copy.deepcopy(replacement)
 return tree

REVIEWED_FINITE_LOG_INVERSE = {'numeric/numeric_tail.py': [('64a77e96dd6f114af7d9113367a67d2a7497513c6d75bacb48b29700e4264942',
                              'if log_disk_bytes:\n'
                              "    caps['tree_bytes'] += log_disk_bytes\n"
                              "    caps['min_free_disk_bytes'] = 8 << 30",
                              '3543b4693a36a1098850b8bc928887694ed59a6deb7d3dfd0339de01f55a77b6',
                              ''),
                             ('cb02e823a36478225353b8c9ac63fe876d3e76d6a9f65cf663bb03db49c4718c',
                              'log_disk_bytes = execution_mode.full_v3_log_disk_bytes(admission, '
                              'dut_profile) if dut_profile is not None else 0\n'
                              'if log_disk_bytes:\n'
                              "    body['extra_bytes'] += log_disk_bytes\n"
                              "    body['write_file_bytes'] = max(body['write_file_bytes'], "
                              'execution_mode.expected_log_policy(admission, '
                              "dut_profile)['compressed_bytes'])",
                              '3543b4693a36a1098850b8bc928887694ed59a6deb7d3dfd0339de01f55a77b6',
                              '')]}
PRE_FINITE_LOG_AST_SHA256 = '5dddebfd904b170ecb27fe1c76d3e8a538114a7775578ce39d6f92d2fb402488'

def undo_reviewed_finite_log_delta(test,tree,relative):
 # Exact finite-log candidate fragments only, reversed before the unchanged
 # V3/V2/historical inverses and before their mutation/duplicate fixtures.
 import copy
 tree=copy.deepcopy(tree)
 for digest,new_text,old_digest,old_text in REVIEWED_FINITE_LOG_INVERSE.get(relative,()):
  want=ast.parse(new_text).body;replacement=ast.parse(old_text).body
  fingerprint=lambda body:hashlib.sha256(ast.dump(ast.Module(body=body,type_ignores=[]),include_attributes=False).encode()).hexdigest()
  test.assertEqual(fingerprint(want),digest,'fixed finite-log fragment')
  test.assertEqual(fingerprint(replacement),old_digest,'fixed pre-finite-log replacement')
  want_dump=[ast.dump(n,include_attributes=False)for n in want];matches=[]
  def visit(node):
   for field,value in ast.iter_fields(node):
    if isinstance(value,list):
     for i in range(len(value)-len(want)+1):
      if all(isinstance(n,ast.AST)for n in value[i:i+len(want)])and [ast.dump(n,include_attributes=False)for n in value[i:i+len(want)]]==want_dump:matches.append((value,i))
     for item in value:
      if isinstance(item,ast.AST):visit(item)
    elif isinstance(value,ast.AST):visit(value)
  visit(tree)
  test.assertEqual(len(matches),1,'one exact finite-log fragment: '+digest)
  container,index=matches[0];container[index:index+len(want)]=copy.deepcopy(replacement)
 return tree

REVIEWED_V3_INVERSE = {'numeric/numeric_tail.py': [['dc70475053412b555de36b2bd2a1953f6cae4aeafed6e6c46d99144940d2358b',
                              "if admission.get('budget_version') == 3:\n"
                              "    return dict(full_budget_sha256=admission['reviewed_budget_sha256'], "
                              '**execution_mode.queue_report_fields(admission))',
                              '3543b4693a36a1098850b8bc928887694ed59a6deb7d3dfd0339de01f55a77b6',
                              '',
                              20],
                             ['cfbb7244f31ae7c434e142d614631f083b71e502c351eb18ea3bfe91e27a7ca6',
                              "if admission.get('budget_version') == 3:\n"
                              '    need(type(profile) is int and profile in '
                              "execution_mode.ready_queue_profiles(admission), 'no launch outside admitted "
                              "ready set')",
                              '3543b4693a36a1098850b8bc928887694ed59a6deb7d3dfd0339de01f55a77b6',
                              '',
                              19],
                             ['0b72d4836026850f1c537c698263c11ab75bf0da797d0e0ad0d073f39729cf66',
                              'selected = profile_policy.eligible(b)\n'
                              "if admission.get('budget_version') == 3:\n"
                              "    need(selected == list(range(5)), 'V3 retains all five registered hardware "
                              "profiles')\n"
                              '    return execution_mode.ready_queue_profiles(admission)',
                              'a7860b6e825d10c68405b2ba5cc58c6b4a03652d802536e22f9732e44451ae57',
                              'selected = profile_policy.eligible(b)',
                              18]]}
PRE_V3_AST_SHA256 = '636bb0b50a1733ae5df7f8a99621244e89f30754eb7226f26d434590cc1efa56'
def undo_reviewed_v3_delta(test,tree,relative):
 # Reverse only the exact reviewed V3 fragments, in reverse author order,
 # before the unchanged V2 and older inverses or their negative fixtures.
 import copy
 tree=copy.deepcopy(tree)
 for digest,new_text,old_digest,old_text,author_index in REVIEWED_V3_INVERSE.get(relative,()):
  want=ast.parse(new_text).body;replacement=ast.parse(old_text).body
  fingerprint=lambda body:hashlib.sha256(ast.dump(ast.Module(body=body,type_ignores=[]),include_attributes=False).encode()).hexdigest()
  test.assertEqual(fingerprint(want),digest,'fixed reviewed V3 fragment')
  test.assertEqual(fingerprint(replacement),old_digest,'fixed pre-V3 replacement')
  want_dump=[ast.dump(n,include_attributes=False)for n in want];matches=[]
  def visit(node):
   for field,value in ast.iter_fields(node):
    if isinstance(value,list):
     for i in range(len(value)-len(want)+1):
      if all(isinstance(n,ast.AST)for n in value[i:i+len(want)])and [ast.dump(n,include_attributes=False)for n in value[i:i+len(want)]]==want_dump:matches.append((value,i))
     for item in value:
      if isinstance(item,ast.AST):visit(item)
    elif isinstance(value,ast.AST):visit(value)
  visit(tree)
  test.assertEqual(len(matches),1,'one exact reviewed V3 fragment: '+digest)
  container,index=matches[0];container[index:index+len(want)]=copy.deepcopy(replacement)
 return tree

# Exact reviewed full-prefill functions only. The prior full-file AST hash below
# still covers every node after reversing these source-reviewed additions.
REVIEWED_FULL_PREFILL_INVERSE = {'execution_command': ('8be015eec2a8e9a24eaf170951bfb80503c39249702014f165e7d70e7a460922',
                       'def execution_command(generated, b, admission, profile):\n'
                       "    need(generated[1] == str(D / 'consumer_owned.py'), 'explicit owned consumer "
                       "handoff')\n"
                       "    need(not any((flag in generated for flag in ('--execution-mode', "
                       "'--calibration-wall-seconds', '--full-block-budget', '--full-block-budget-sha256', "
                       "'--stage-coverage-budget', '--stage-coverage-budget-sha256'))), 'no stale or "
                       "duplicate execution mode arguments')\n"
                       "    argv = list(generated) + ['--execution-mode', admission['mode']]\n"
                       "    if admission['mode'] == execution_mode.CALIBRATION:\n"
                       "        argv += ['--calibration-wall-seconds', "
                       "str(admission['profile_seconds'][str(profile)])]\n"
                       "    elif admission['mode'] == execution_mode.FIRST_FAULT:\n"
                       "        need(profile == 0 and admission.get('diagnostic_profiles') == [0] and "
                       "(b.get('execution_context') == 'CLOUD_EXECUTOR_V1') and (b.get('full_block_budget') "
                       "is None) and (b.get('stage_coverage_budget') is None), 'only approved P0 first-fault "
                       "diagnostic')\n"
                       "    elif admission['mode'] == execution_mode.STAGE:\n"
                       "        need(b.get('execution_context') == 'CLOUD_EXECUTOR_V1' and "
                       "b.get('full_block_budget') is None, 'stage coverage is cloud-only, not full "
                       "acceptance')\n"
                       "        budget = b['stage_coverage_budget']\n"
                       "        argv += ['--stage-coverage-budget', budget['path'], "
                       "'--stage-coverage-budget-sha256', budget['sha256']]\n"
                       '    else:\n'
                       "        need(admission['mode'] == execution_mode.FULL, 'explicit execution mode')\n"
                       "        budget = b['full_block_budget']\n"
                       "        argv += ['--full-block-budget', budget['path'], "
                       "'--full-block-budget-sha256', budget['sha256']]\n"
                       "    if b.get('execution_context') == 'CLOUD_EXECUTOR_V1':\n"
                       "        invocation = b['controller_binding']\n"
                       '        material.checked(invocation)\n'
                       "        flags = ('--cloud-binding', '--cloud-binding-sha256')\n"
                       '        if any((flag in argv for flag in flags)):\n'
                       "            need(all((argv.count(flag) == 1 for flag in flags)), 'exact one paired "
                       "generated cloud invocation')\n"
                       '            need(all((argv.index(flag) + 1 < len(argv) for flag in flags)), '
                       "'generated cloud invocation values')\n"
                       "            need(argv[argv.index(flags[0]) + 1] == invocation['path'] and "
                       "argv[argv.index(flags[1]) + 1] == invocation['sha256'], 'generated cloud invocation "
                       "unchanged')\n"
                       '        else:\n'
                       "            argv += ['--cloud-binding', invocation['path'], "
                       "'--cloud-binding-sha256', invocation['sha256']]\n"
                       "    return (argv, admission['profile_seconds'][str(profile)] + 30)"),
 'run': ('560d5fc1466b61548dfa6573f9ae04a7f54ae670b0b47e16826a2c65632a10c6',
         'def run(b, binding_path, binding_sha):\n'
         '    validate(b)\n'
         '    cloud = cloud_context(b)\n'
         '    retained = retained_context(b)\n'
         '    admission = execution_mode.admit(b)\n'
         "    profile_policy.require_source_pin(b['pins'])\n"
         "    pins = dict(b['pins'])\n"
         '    pins[str(binding_path)] = binding_sha\n'
         "    need(pins.get(str(D.parent / 'execution_mode.py')) == sha(D.parent / 'execution_mode.py'), "
         "'execution mode source pin')\n"
         "    need(not {r['pin']['path'] for r in b['weights']} & set(pins), 'large payload uses streaming "
         "pins, not supervisor read_bytes')\n"
         '    for p, h in pins.items():\n'
         "        need(sha(p) == h, 'source pin drift')\n"
         "    for name in ('supervise_multiroot.py', 'strict_cleanup.py', 'lossless_log.py'):\n"
         "        path = str(P(b['supervisor_dir']) / name)\n"
         "        need(pins.get(path) == sha(path), 'exact published supervisor closure')\n"
         "    for name in ('required_acceptance.py', 'numeric_tail.py', 'provider_from_frozen.py', "
         "'locked_phase.py', 'live_budget.py', 'consumer_owned.py', 'dut_evidence.py', "
         "'runtime_abi_owned.py', 'connect_owned.py', 'CONNECTION_OWNED_SOURCE_PINS.json'):\n"
         "        need(pins.get(str(D / name)) == sha(D / name), 'controller source pin')\n"
         "    out = P(b['output'])\n"
         "    roots = live_budget.roots_checked(b['owned_roots'])\n"
         "    for role in ('repo', 'owner_root', 'payload'):\n"
         "        need(any((P(b[role]).resolve().is_relative_to(r) for r in roots)), 'unwatched required "
         "material ' + role)\n"
         "    build_pin = b['builder_handoff'] if cloud is not None else b['build_result']\n"
         "    need(any((P(build_pin['path']).resolve().is_relative_to(r) for r in roots)), 'unwatched build "
         "evidence')\n"
         '    if cloud is None:\n'
         "        build = material.checked(b['build_result'])\n"
         '        br = json.loads(build.read_text())\n'
         "        manifest = material.checked(br['artifact']['manifest'])\n"
         '        frozen = json.loads(manifest.read_text())\n'
         "        proof = module('same_job_proof', D / 'local_build_proof.py', pins)\n"
         "        proof.verify(build, b['build_result']['sha256'], manifest, sha(manifest), frozen, "
         "b['run_id'], b['launch_commit'], b['source_commit'])\n"
         '    else:\n'
         '        build = None\n'
         "        manifest = material.checked(b['artifact_manifest'])\n"
         '        frozen = json.loads(manifest.read_text())\n'
         "        candidate = frozen['schema'] in ('MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1', "
         "'MODEL_CANDIDATE_FIRST_FAULT_BUILD_ARTIFACT_V1')\n"
         "        proof = module('split_build_proof', D / ('candidate_artifact_handoff.py' if candidate else "
         "'artifact_handoff.py'), pins)\n"
         "        kwargs = dict(executor_adaptation=b.get('executor_adaptation'))\n"
         '        if candidate:\n'
         "            kwargs.update(model_candidate_review=b.get('model_candidate_review'), "
         "current_source_pins_pin=b['source_pins'], repo=b['repo'])\n"
         "        proof.verify(b['builder_handoff']['path'], b['builder_handoff']['sha256'], manifest, "
         'sha(manifest), frozen, cloud, **kwargs)\n'
         "    need(not out.exists() and out.is_relative_to(P(b['owner_root'])), 'fresh output inside runtime "
         "owner')\n"
         '    out.mkdir()\n'
         "    (out / 'runs').mkdir()\n"
         "    (out / 'phases').mkdir()\n"
         "    (out / 'cache_roots').mkdir()\n"
         "    save(out / 'REGISTERED_FIVE.json', dict(execution_policy=profile_policy.checked(b), "
         "profiles=b['profiles'], tokens=128, execution_mode=admission['mode'], "
         "profile_seconds=admission['profile_seconds'], **mode_budget_fields(admission), "
         "scope='CHISEL_EMITTED_SV_SIMULATION_NOT_FINAL_RTL', numeric_pass=False))\n"
         "    sys.path.insert(0, b['supervisor_dir'])\n"
         '    import supervise_multiroot as supervisor\n'
         "    owner = module('admitted_runtime_owner', P(b['owner_module']), pins)\n"
         "    owner_doc, _ = owner.verify(b['owner_manifest']['path'], b['owner_manifest']['sha256'], "
         "b['owner_root'])\n"
         "    need(owner_doc['schema'] in (('SHARED_THREE_RUNTIME_OWNER_FRESH_JOB_V3', "
         "'IMPORTED_THREE_RUNTIME_OWNER_CLOUD_V1') if cloud is not None else "
         "('SHARED_THREE_RUNTIME_OWNER_FRESH_JOB_V3',)) and owner_doc['identity'] == (cloud if cloud is not "
         "None else dict(run_id=b['run_id'], source_commit=b['source_commit'], "
         "launch_commit=b['launch_commit'])), 'fresh CI owner exact same run/source/launch, never historical "
         "V2 receipt')\n"
         '    profile_policy.require_same(b, owner_doc)\n'
         '    reference_reuse = None\n'
         '    reference_reuse_context = None\n'
         '    reference_reuse_source_pin = None\n'
         "    if b.get('reference_data_reuse') is not None:\n"
         "        reference_reuse = module('tail_reference_data_reuse', D / 'reference_data_reuse.py', "
         'pins)\n'
         "        reference_reuse_context = {key: b[key] for key in ('repo', 'artifact_manifest', "
         "'retained_materials')}\n"
         "        if admission['mode'] == execution_mode.FIRST_FAULT:\n"
         "            reference_reuse_context['execution_mode'] = execution_mode.FIRST_FAULT\n"
         "        reference_reuse_source_pin = material.pin(D / 'reference_data_reuse.py')\n"
         "        verified_reference = reference_reuse.verify_metadata(b['reference_data_reuse'], "
         'reference_reuse_context)\n'
         "        need(verified_reference['tree_cap'] == b['tree_cap'], 'actual reference reuse tree cap')\n"
         '        need(all((any((P(p).resolve().is_relative_to(r) for r in roots)) for p in '
         "verified_reference['roots'])), 'all reference data and evidence watched')\n"
         "    common = frozen['common']\n"
         '    root = manifest.parent\n'
         '    allstage = []\n'
         '    dut_records = []\n'
         '\n'
         '    def stage(name, argv, seconds=None, accepted=(0,), lease_out=None):\n'
         "        seconds = seconds or b['provider_wall_seconds']\n"
         "        phase = out / 'phases' / (name + '.json')\n"
         "        run_dir = out / 'runs' / name\n"
         "        cache_root = out / 'cache_roots' / name\n"
         "        e = owned_environment(b['environment'], cache_root)\n"
         "        body = dict(argv=list(map(str, argv)), pins=pins, owned_roots=b['owned_roots'], "
         "extra_bytes=b['phase_extra_bytes'], seconds=seconds, job_started=b['job_started_monotonic'], "
         "job_budget_seconds=b['job_budget_seconds'] if cloud is not None else 21000, write_file_bytes=128 "
         "<< 20, tree_cap=b['tree_cap'], environment=e, cache_root=str(cache_root), "
         "admission_output=str(run_dir / 'LIVE_ADMISSION.json'))\n"
         '        save(phase, body)\n'
         '        localpins = dict(pins)\n'
         '        localpins[str(phase)] = sha(phase)\n'
         '        caps = dict(wall_seconds=seconds + 30, cleanup_seconds=30, file_bytes=2 << 30, '
         'tree_bytes=512 << 20, log_bytes=64 << 20, raw_log_bytes=128 << 20, max_entries=100000, '
         "per_process_as_bytes=b['address_space_bytes'], per_process_cpu_seconds=18000 if "
         "name.endswith('_dut') else seconds + 30, rss_bytes=b['rss_bytes'], cpu_seconds=seconds + 30, "
         "extra_watch_roots=b['owned_roots'], min_free_disk_bytes=1500000000, "
         "watch_tree_bytes=b['tree_cap'])\n"
         "        r = supervisor.execute([b['python'], '-B', str(D / 'locked_phase.py'), '--phase', "
         "str(phase), '--sha256', sha(phase)], str(run_dir), b['lock'], caps, e, localpins, "
         "resource_gate={'min_available_memory': b['rss_bytes'] + (1 << 30) + "
         "(b['reserved_other_owner_bytes'] if cloud is not None else 0), 'min_disk_free': 8 << 30})\n"
         "        save(out / 'phases' / (name + '_SUPERVISOR_RETURN.json'), r)\n"
         "        require_cleanup(r, out / ('OWNERSHIP_INCOMPLETE_' + name + '.json'), run_dir, "
         'P(supervisor.__file__))\n'
         "        allstage.append(dict(name=name, native_exit=r['native_exit'], receipt_sha256=sha(run_dir / "
         "'RESULT.json')))\n"
         "        need(r['native_exit'] in accepted and (not r['errors']), 'stage failed; no retry ' + "
         'name)\n'
         '        return r\n'
         "    stable_cache = out / 'execution_cache'\n"
         '    owned_environment({}, stable_cache)\n'
         "    env_manifest = out / 'EXECUTION_ENVIRONMENT.json'\n"
         "    save(env_manifest, dict(schema='OWNED_EXECUTION_ENVIRONMENT_V1', identity=cloud if cloud is "
         "not None else dict(run_id=b['run_id'], source_commit=b['source_commit'], "
         "launch_commit=b['launch_commit']), owner_root=b['owner_root'], watched_roots=[b['owner_root']], "
         'cache_root=str(stable_cache), cache_paths={k: str(stable_cache / k.lower()) for k in '
         'CACHE_NAMES}))\n'
         '    pins[str(env_manifest)] = sha(env_manifest)\n'
         "    env_args = ['--owned-environment', str(env_manifest), '--owned-environment-sha256', "
         'sha(env_manifest)]\n'
         '    if cloud is not None:\n'
         "        identity_pin = b['executor_identity_pin']\n"
         '        material.checked(identity_pin)\n'
         "        need(json.loads(P(identity_pin['path']).read_text()) == cloud, 'actual executor identity "
         "bytes')\n"
         "        env_args += ['--executor-identity', identity_pin['path'], '--executor-identity-sha256', "
         "identity_pin['sha256']]\n"
         '    abi_extra = []\n'
         "    if b.get('workspace_loader') is not None:\n"
         "        for name in ('workspace_loader', 'executor_adaptation'):\n"
         '            row = b[name]\n'
         '            material.checked(row)\n'
         "            abi_extra += ['--' + name.replace('_', '-'), row['path'], '--' + name.replace('_', "
         "'-') + '-sha256', row['sha256']]\n"
         "        abi_extra += ['--artifact-manifest-sha256', sha(manifest)]\n"
         "    abi = out / 'STARTUP_ABI.json'\n"
         "    tool = frozen['tool_manifest']\n"
         "    binary = common['binary']\n"
         "    stage('startup_abi', [b['python'], '-B', str(D / 'runtime_abi_owned.py'), '--binary', str(root "
         "/ binary['path']), '--binary-sha256', binary['sha256'], '--tool-manifest', str(root / "
         "tool['path']), '--tool-manifest-sha256', tool['sha256'], '--output', str(abi), "
         "'--execute-reviewed-loader-list', '--expected-run-id', str(b['run_id']), "
         "'--expected-source-commit', b['source_commit'], '--expected-launch-commit', b['launch_commit'], "
         '*env_args, *abi_extra], 120)\n'
         "    identity_args = ['--artifact-manifest', str(manifest), '--artifact-manifest-sha256', "
         "sha(manifest), '--expected-run-id', str(b['run_id']), '--expected-launch-commit', "
         "b['launch_commit'], '--expected-source-commit', b['source_commit'], '--local-runtime-abi', "
         "str(abi), '--local-runtime-abi-sha256', sha(abi), *env_args]\n"
         '    if cloud is None:\n'
         "        identity_args += ['--local-build-result', str(build), '--local-build-result-sha256', "
         "b['build_result']['sha256']]\n"
         '    else:\n'
         "        identity_args += ['--builder-handoff', b['builder_handoff']['path'], "
         "'--builder-handoff-sha256', b['builder_handoff']['sha256'], '--cloud-binding', "
         "b['controller_binding']['path'], '--cloud-binding-sha256', b['controller_binding']['sha256']]\n"
         '    for i in execution_profiles(b, admission):\n'
         "        lease_root = out / f'profile{i}'\n"
         '        lease_root.mkdir()\n'
         "        profile = lease_root / 'material'\n"
         "        with owner.lease(b['owner_manifest']['path'], b['owner_manifest']['sha256'], "
         "b['owner_root'], i, lease_root) as selected:\n"
         '            weights(b, i)\n'
         "            runtime = selected[('qwen2', 'qwen35_08b', 'qwen35_08b', 'qwen35_35b', "
         "'qwen35_35b')[i]]\n"
         '            ref_path = reference_path(b, i, retained)\n'
         '            ref_doc = json.loads(ref_path.read_text())\n'
         "            need(ref_doc['runtime_receipt_sha256'] == runtime['receipt']['sha256'] and "
         "ref_doc['runtime_source_pins_sha256'] == runtime['sidecar']['sha256'], 'reference matches actual "
         "selected installed runtime/sidecar')\n"
         '\n'
         '            def provider_stage(label, argv):\n'
         "                return stage(f'p{i}_{label}', argv, lease_out=lease_root)\n"
         "            initialization = out / 'phases' / f'p{i}_initialize_input.json'\n"
         "            initialize_body = dict(repo=b['repo'], materializer=b['materializer'], "
         "output=str(profile), profile=i, reference=b['references'][str(i)])\n"
         '            if reference_reuse is not None:\n'
         "                initialize_body.update(reference_data_reuse=b['reference_data_reuse'], "
         'reference_reuse_context=reference_reuse_context, '
         'reference_reuse_source_pin=reference_reuse_source_pin)\n'
         '            save(initialization, initialize_body)\n'
         "            stage(f'p{i}_initialize', [b['python'], '-B', str(D / 'provider_from_frozen.py'), "
         "'--initialize-binding', str(initialization), '--sha256', sha(initialization)], 120, "
         'lease_out=lease_root)\n'
         "            material.prepare(b['repo'], b['materializer'], profile, i, runtime['wrapper'], "
         "b['payload'], b['references'][str(i)], provider_stage, pins, "
         "p0_provider_reuse=b.get('p0_provider_reuse') if i == 0 else None)\n"
         "            stage(f'p{i}_connect', [b['python'], '-B', str(D / 'connect_owned.py'), "
         "'--existing-output', str(profile), '--profile', str(i), *identity_args], 120, "
         'lease_out=lease_root)\n'
         "            generated = json.loads((profile / 'CONSUMER_ARGV.json').read_text())['consumer_argv']\n"
         '            generated, outer_seconds = execution_command(generated, b, admission, i)\n'
         '            if reference_reuse is not None:\n'
         '                verify_reference_with_deadline(b, reference_reuse, profile, i, '
         'reference_reuse_context)\n'
         "            dut_outer = stage(f'p{i}_dut', generated, outer_seconds, accepted=(1, 2), "
         'lease_out=lease_root)\n'
         '            if reference_reuse is not None:\n'
         '                verify_reference_with_deadline(b, reference_reuse, profile, i, '
         'reference_reuse_context)\n'
         "            bundle = profile / 'runtime_bundle.v3.json'\n"
         '            bundle_doc = json.loads(bundle.read_text())\n'
         "            runtime_sha = bundle_doc['profiles'][0]['runtime']['sha256']\n"
         "            diagnostic = dut_evidence.verify(profile / 'dut_result', i, sha(manifest), "
         "sha(bundle), binary['sha256'], runtime_sha, material.pin(out / 'runs' / f'p{i}_dut' / "
         "'RESULT.json'))\n"
         '            if cloud is not None:\n'
         "                report = json.loads((profile / 'dut_result/RESULT.json').read_text())\n"
         "                need(report.get('executor_identity') == cloud and "
         "report.get('builder_handoff_sha256') == b['builder_handoff']['sha256'], 'actual executor report "
         "not builder identity')\n"
         "                if b.get('executor_adaptation') is not None:\n"
         "                    need(report.get('executor_adaptation_sha256') == "
         "b['executor_adaptation']['sha256'] and report.get('workspace_loader_sha256') == "
         "b['workspace_loader']['sha256'], 'actual executor adapter/loader provenance')\n"
         "            if admission['mode'] in (execution_mode.FULL, execution_mode.STAGE, "
         'execution_mode.FIRST_FAULT):\n'
         "                report = json.loads((profile / 'dut_result/RESULT.json').read_text())\n"
         "                actual = report['execution_admission']\n"
         "                need(actual['execution_mode'] == admission['mode'] and "
         "actual['reviewed_budget_sha256'] == admission['reviewed_budget_sha256'], 'actual consumer "
         "full-mode budget identity')\n"
         "                scope = 'P0_FIRST_FAULT_READONLY_SAME_FULL_M128_STIMULUS_NOT_NUMERICAL_ACCEPTANCE' "
         "if admission['mode'] == execution_mode.FIRST_FAULT else "
         "'STAGE_COVERAGE_DIAGNOSTIC_NOT_FULL_ACCEPTANCE' if admission['mode'] == execution_mode.STAGE else "
         "'FULL_BLOCK_ACCEPTANCE_REQUIRED_TERMINAL_AND_REFERENCE'\n"
         "                need(actual['scope'] == scope and actual['outer_cleanup_proof_required'] is True, "
         "'actual explicit execution scope')\n"
         "                if admission['mode'] == execution_mode.STAGE:\n"
         "                    need(actual.get('stage_budget_sha256') == admission['reviewed_budget_sha256'], "
         "'actual stage coverage budget identity')\n"
         "                if admission['mode'] == execution_mode.FIRST_FAULT:\n"
         "                    need(actual.get('first_fault_document_sha256') == "
         "admission['reviewed_budget_sha256'] and actual.get('stage_budget_sha256') is None, 'actual "
         "first-fault document identity')\n"
         "                expected_limits = report_effective_limits(actual['original_limits'], b, admission, "
         'i)\n'
         "                need(actual['effective_limits'] == expected_limits, 'actual full watchdog "
         "limits')\n"
         '            dut_records.append(diagnostic)\n'
         "            save(out / f'PROFILE_{i}_DIAGNOSTIC.json', diagnostic)\n"
         '            weights(b, i)\n'
         '    qualification = required_acceptance.aggregate(dut_records)\n'
         "    save(out / 'RESULT.json', dict(execution_mode=admission['mode'], "
         '**mode_budget_fields(admission), qualification=qualification, '
         "execution_policy=profile_policy.checked(b), status=qualification['status'], "
         "scope='CHISEL_GENERATED_SIMULATION_BACKEND_NOT_FINAL_RTL', stages=allstage, "
         "profiles=b['profiles'], actual_dut_reports=dut_records, "
         "numerical_pass=qualification['numerical_pass'], "
         "moe_contract='ORIGINAL_TORCH_TOPK_PENDING_SMALL_ID_ACCEPTANCE', uploaded_payloads=False))"),
 'validate': ('a757f51228bd3aea3caba414c9873c41a52c51da4f8533f0f500605d3a153e64',
              'def validate(b):\n'
              "    need(b['schema'] == 'SAME_JOB_FIVE_M128_DIAGNOSTIC_TAIL_V1', 'explicit samejob tail')\n"
              "    need(b['profiles'] == list(range(5)) and b['tokens'] == 128 and (b['matrix_macs'] == "
              "4096) and (b['vector_lanes'] == 32), 'five fixed full profiles')\n"
              "    need(b['upload_payloads'] is False and b['final_rtl_replay'] is False, 'local generated "
              "Chisel test backend only')\n"
              "    profile_policy.require_references(b, b['references'])\n"
              '    cloud = cloud_context(b)\n'
              '    admission = execution_mode.admit(b)\n'
              "    need(b['job_started_monotonic'] <= time.monotonic(), 'owning job start clock, not reset "
              "after build')\n"
              "    need(sum(admission['profile_seconds'].values()) + b['reserved_material_seconds'] + "
              "b['reserved_cleanup_seconds'] + b['reserved_parent_seconds'] <= (b['job_budget_seconds'] if "
              "cloud is not None else 21000) - (time.monotonic() - b['job_started_monotonic']), 'whole five "
              "round exceeds remaining job')\n"
              "    need(b['reserved_material_seconds'] >= 7 * b['provider_wall_seconds'] + 11 * 120 and "
              "b['reserved_cleanup_seconds'] >= 23 * 60 + 5 * 30 and (b['reserved_parent_seconds'] > 0), "
              "'all seven provider/five connect/ABI and twenty-three cleanup plus DUT/parent reservations')\n"
              "    if b.get('reference_data_reuse') is None:\n"
              "        need(b['tree_cap'] == live_budget.TREE_CAP, 'unchanged aggregate tree cap')\n"
              '    else:\n'
              "        need(cloud is not None and b['execution_mode'] in (execution_mode.STAGE, "
              "execution_mode.FIRST_FAULT) and (b['tree_cap'] == 12037043872), 'exact reference-data-only "
              "tree reduction')\n"
              "    for k in ('rss_bytes', 'address_space_bytes', 'phase_extra_bytes', "
              "'provider_wall_seconds'):\n"
              "        need(type(b[k]) is int and b[k] > 0, 'explicit reviewed resource bound ' + k)\n"
              "    need(b['rss_bytes'] <= 12 * 1024 ** 3 and (b['address_space_bytes'] > 0 if cloud is not "
              "None else b['address_space_bytes'] >= 12 * 1024 ** 3) and (b['address_space_bytes'] <= 16 * "
              "1024 ** 3), 'runner resource maxima')")}
def undo_reviewed_full_prefill_delta(test,tree):
 for name,(digest,old_text)in REVIEWED_FULL_PREFILL_INVERSE.items():
  matches=[(i,node)for i,node in enumerate(tree.body)if isinstance(node,ast.FunctionDef)and node.name==name]
  test.assertEqual(len(matches),1,'one exact full-prefill function '+name)
  i,node=matches[0]
  test.assertEqual(hashlib.sha256(ast.dump(node,include_attributes=False).encode()).hexdigest(),digest,'reviewed full-prefill function bytes '+name)
  tree.body[i]=ast.parse(old_text).body[0]
 return tree

REVIEWED_FIRST_FAULT_INVERSE = {'numeric/numeric_tail.py': [['8b36c4832459be16aca77c6b2673700334ee3d491b543b60a5b52e283f99a9c8',
                              "if b.get('reference_data_reuse') is not None:\n"
                              "    need(b['execution_mode'] in (execution_mode.STAGE, "
                              "execution_mode.FIRST_FAULT) and b.get('model_candidate_review') is "
                              "not None, 'reference reuse only approved candidate stage "
                              "coverage')\n"
                              "if b.get('p0_provider_reuse') is not None:\n"
                              "    need(b['execution_mode'] in (execution_mode.STAGE, "
                              "execution_mode.FIRST_FAULT) and b.get('model_candidate_review') is "
                              "not None, 'P0 reuse only approved candidate stage coverage')",
                              "if b.get('reference_data_reuse') is not None:\n"
                              "    need(b['execution_mode'] == execution_mode.STAGE and "
                              "b.get('model_candidate_review') is not None, 'reference reuse only "
                              "approved candidate stage coverage')\n"
                              "if b.get('p0_provider_reuse') is not None:\n"
                              "    need(b['execution_mode'] == execution_mode.STAGE and "
                              "b.get('model_candidate_review') is not None, 'P0 reuse only "
                              "approved candidate stage coverage')"],
                             ['f9c4ab85ba0089d2b0f20c27f6d1100e098a01f281b797543b8b43c3899136a8',
                              "need(cloud is not None and b['execution_mode'] in "
                              '(execution_mode.STAGE, execution_mode.FIRST_FAULT) and '
                              "(b['tree_cap'] == 12037043872), 'exact reference-data-only tree "
                              "reduction')",
                              "need(cloud is not None and b['execution_mode'] == "
                              "execution_mode.STAGE and (b['tree_cap'] == 12037043872), 'exact "
                              "reference-data-only tree reduction')"],
                             ['e14a233fa3cbed06c5f25b4a1b5d3f0214ef465710c57813a1b7ab1104184093',
                              'def execution_profiles(b, admission):\n'
                              '    selected = profile_policy.eligible(b)\n'
                              "    if admission['mode'] == execution_mode.FIRST_FAULT:\n"
                              '        need(selected == list(range(5)) and '
                              "admission.get('diagnostic_profiles') == [0] and "
                              "(type(admission['diagnostic_profiles'][0]) is int), 'registered "
                              "hardware unchanged; only integer P0 selected')\n"
                              '        return [0]\n'
                              '    return selected',
                              ''],
                             ['7fca2d91ad540d1a312208082b2e0ec8243754ee2ef394a7adfbf6f1ae694ce2',
                              "if admission['mode'] == execution_mode.FIRST_FAULT:\n"
                              "    need(profile == 0 and admission.get('diagnostic_profiles') == "
                              "[0] and (b.get('execution_context') == 'CLOUD_EXECUTOR_V1') and "
                              "(b.get('full_block_budget') is None) and "
                              "(b.get('stage_coverage_budget') is None), 'only approved P0 "
                              "first-fault diagnostic')\n"
                              "elif admission['mode'] == execution_mode.STAGE:\n"
                              "    need(b.get('execution_context') == 'CLOUD_EXECUTOR_V1' and "
                              "b.get('full_block_budget') is None, 'stage coverage is cloud-only, "
                              "not full acceptance')\n"
                              "    budget = b['stage_coverage_budget']\n"
                              "    argv += ['--stage-coverage-budget', budget['path'], "
                              "'--stage-coverage-budget-sha256', budget['sha256']]\n"
                              'else:\n'
                              "    need(admission['mode'] == execution_mode.FULL, 'explicit "
                              "execution mode')\n"
                              "    budget = b['full_block_budget']\n"
                              "    argv += ['--full-block-budget', budget['path'], "
                              "'--full-block-budget-sha256', budget['sha256']]",
                              "if admission['mode'] == execution_mode.STAGE:\n"
                              "    need(b.get('execution_context') == 'CLOUD_EXECUTOR_V1' and "
                              "b.get('full_block_budget') is None, 'stage coverage is cloud-only, "
                              "not full acceptance')\n"
                              "    budget = b['stage_coverage_budget']\n"
                              "    argv += ['--stage-coverage-budget', budget['path'], "
                              "'--stage-coverage-budget-sha256', budget['sha256']]\n"
                              'else:\n'
                              "    need(admission['mode'] == execution_mode.FULL, 'explicit "
                              "execution mode')\n"
                              "    budget = b['full_block_budget']\n"
                              "    argv += ['--full-block-budget', budget['path'], "
                              "'--full-block-budget-sha256', budget['sha256']]"],
                             ['1f5500348daa0072d69ddb2469615393911d8e10e6608ab37e8cde7fbcb6f3e9',
                              "if admission['mode'] == execution_mode.FIRST_FAULT:\n"
                              '    return dict(full_budget_sha256=None, stage_budget_sha256=None, '
                              "first_fault_document_sha256=admission['reviewed_budget_sha256'], "
                              'diagnostic_profiles=[0], not_selected_profiles=[1, 2, 3, 4])',
                              ''],
                             ['3bde705240a9fd128040a7838b3bd250aea00cf2eaa73f1b8434af0a0c25cc7c',
                              "candidate = frozen['schema'] in "
                              "('MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1', "
                              "'MODEL_CANDIDATE_FIRST_FAULT_BUILD_ARTIFACT_V1')",
                              "candidate = frozen['schema'] == "
                              "'MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1'"],
                             ['bf9d2397d9ba4eecf848186a912f0e7cc205fbbb9dc105c35aa2cd66a167f86e',
                              "if admission['mode'] == execution_mode.FIRST_FAULT:\n"
                              "    reference_reuse_context['execution_mode'] = "
                              'execution_mode.FIRST_FAULT',
                              ''],
                             ['199cde439e342d61061eecad7fe866207eeb36e90a61c0c769970b55dbc08328',
                              'for i in execution_profiles(b, admission):\n'
                              "    lease_root = out / f'profile{i}'\n"
                              '    lease_root.mkdir()\n'
                              "    profile = lease_root / 'material'\n"
                              "    with owner.lease(b['owner_manifest']['path'], "
                              "b['owner_manifest']['sha256'], b['owner_root'], i, lease_root) as "
                              'selected:\n'
                              '        weights(b, i)\n'
                              "        runtime = selected[('qwen2', 'qwen35_08b', 'qwen35_08b', "
                              "'qwen35_35b', 'qwen35_35b')[i]]\n"
                              '        ref_path = reference_path(b, i, retained)\n'
                              '        ref_doc = json.loads(ref_path.read_text())\n'
                              "        need(ref_doc['runtime_receipt_sha256'] == "
                              "runtime['receipt']['sha256'] and "
                              "ref_doc['runtime_source_pins_sha256'] == "
                              "runtime['sidecar']['sha256'], 'reference matches actual selected "
                              "installed runtime/sidecar')\n"
                              '\n'
                              '        def provider_stage(label, argv):\n'
                              "            return stage(f'p{i}_{label}', argv, "
                              'lease_out=lease_root)\n'
                              "        initialization = out / 'phases' / "
                              "f'p{i}_initialize_input.json'\n"
                              "        initialize_body = dict(repo=b['repo'], "
                              "materializer=b['materializer'], output=str(profile), profile=i, "
                              "reference=b['references'][str(i)])\n"
                              '        if reference_reuse is not None:\n'
                              '            '
                              "initialize_body.update(reference_data_reuse=b['reference_data_reuse'], "
                              'reference_reuse_context=reference_reuse_context, '
                              'reference_reuse_source_pin=reference_reuse_source_pin)\n'
                              '        save(initialization, initialize_body)\n'
                              "        stage(f'p{i}_initialize', [b['python'], '-B', str(D / "
                              "'provider_from_frozen.py'), '--initialize-binding', "
                              "str(initialization), '--sha256', sha(initialization)], 120, "
                              'lease_out=lease_root)\n'
                              "        material.prepare(b['repo'], b['materializer'], profile, i, "
                              "runtime['wrapper'], b['payload'], b['references'][str(i)], "
                              "provider_stage, pins, p0_provider_reuse=b.get('p0_provider_reuse') "
                              'if i == 0 else None)\n'
                              "        stage(f'p{i}_connect', [b['python'], '-B', str(D / "
                              "'connect_owned.py'), '--existing-output', str(profile), "
                              "'--profile', str(i), *identity_args], 120, lease_out=lease_root)\n"
                              '        generated = json.loads((profile / '
                              "'CONSUMER_ARGV.json').read_text())['consumer_argv']\n"
                              '        generated, outer_seconds = execution_command(generated, b, '
                              'admission, i)\n'
                              '        if reference_reuse is not None:\n'
                              '            verify_reference_with_deadline(b, reference_reuse, '
                              'profile, i, reference_reuse_context)\n'
                              "        dut_outer = stage(f'p{i}_dut', generated, outer_seconds, "
                              'accepted=(1, 2), lease_out=lease_root)\n'
                              '        if reference_reuse is not None:\n'
                              '            verify_reference_with_deadline(b, reference_reuse, '
                              'profile, i, reference_reuse_context)\n'
                              "        bundle = profile / 'runtime_bundle.v3.json'\n"
                              '        bundle_doc = json.loads(bundle.read_text())\n'
                              '        runtime_sha = '
                              "bundle_doc['profiles'][0]['runtime']['sha256']\n"
                              "        diagnostic = dut_evidence.verify(profile / 'dut_result', i, "
                              "sha(manifest), sha(bundle), binary['sha256'], runtime_sha, "
                              "material.pin(out / 'runs' / f'p{i}_dut' / 'RESULT.json'))\n"
                              '        if cloud is not None:\n'
                              '            report = json.loads((profile / '
                              "'dut_result/RESULT.json').read_text())\n"
                              "            need(report.get('executor_identity') == cloud and "
                              "report.get('builder_handoff_sha256') == "
                              "b['builder_handoff']['sha256'], 'actual executor report not builder "
                              "identity')\n"
                              "            if b.get('executor_adaptation') is not None:\n"
                              "                need(report.get('executor_adaptation_sha256') == "
                              "b['executor_adaptation']['sha256'] and "
                              "report.get('workspace_loader_sha256') == "
                              "b['workspace_loader']['sha256'], 'actual executor adapter/loader "
                              "provenance')\n"
                              "        if admission['mode'] in (execution_mode.FULL, "
                              'execution_mode.STAGE, execution_mode.FIRST_FAULT):\n'
                              '            report = json.loads((profile / '
                              "'dut_result/RESULT.json').read_text())\n"
                              "            actual = report['execution_admission']\n"
                              "            need(actual['execution_mode'] == admission['mode'] and "
                              "actual['reviewed_budget_sha256'] == "
                              "admission['reviewed_budget_sha256'], 'actual consumer full-mode "
                              "budget identity')\n"
                              '            scope = '
                              "'P0_FIRST_FAULT_READONLY_SAME_FULL_M128_STIMULUS_NOT_NUMERICAL_ACCEPTANCE' "
                              "if admission['mode'] == execution_mode.FIRST_FAULT else "
                              "'STAGE_COVERAGE_DIAGNOSTIC_NOT_FULL_ACCEPTANCE' if "
                              "admission['mode'] == execution_mode.STAGE else "
                              "'FULL_BLOCK_ACCEPTANCE_REQUIRED_TERMINAL_AND_REFERENCE'\n"
                              "            need(actual['scope'] == scope and "
                              "actual['outer_cleanup_proof_required'] is True, 'actual explicit "
                              "execution scope')\n"
                              "            if admission['mode'] == execution_mode.STAGE:\n"
                              "                need(actual.get('stage_budget_sha256') == "
                              "admission['reviewed_budget_sha256'], 'actual stage coverage budget "
                              "identity')\n"
                              "            if admission['mode'] == execution_mode.FIRST_FAULT:\n"
                              "                need(actual.get('first_fault_document_sha256') == "
                              "admission['reviewed_budget_sha256'] and "
                              "actual.get('stage_budget_sha256') is None, 'actual first-fault "
                              "document identity')\n"
                              '            expected_limits = '
                              "report_effective_limits(actual['original_limits'], b, admission, "
                              'i)\n'
                              "            need(actual['effective_limits'] == expected_limits, "
                              "'actual full watchdog limits')\n"
                              '        dut_records.append(diagnostic)\n'
                              "        save(out / f'PROFILE_{i}_DIAGNOSTIC.json', diagnostic)\n"
                              '        weights(b, i)',
                              'for i in profile_policy.eligible(b):\n'
                              "    lease_root = out / f'profile{i}'\n"
                              '    lease_root.mkdir()\n'
                              "    profile = lease_root / 'material'\n"
                              "    with owner.lease(b['owner_manifest']['path'], "
                              "b['owner_manifest']['sha256'], b['owner_root'], i, lease_root) as "
                              'selected:\n'
                              '        weights(b, i)\n'
                              "        runtime = selected[('qwen2', 'qwen35_08b', 'qwen35_08b', "
                              "'qwen35_35b', 'qwen35_35b')[i]]\n"
                              '        ref_path = reference_path(b, i, retained)\n'
                              '        ref_doc = json.loads(ref_path.read_text())\n'
                              "        need(ref_doc['runtime_receipt_sha256'] == "
                              "runtime['receipt']['sha256'] and "
                              "ref_doc['runtime_source_pins_sha256'] == "
                              "runtime['sidecar']['sha256'], 'reference matches actual selected "
                              "installed runtime/sidecar')\n"
                              '\n'
                              '        def provider_stage(label, argv):\n'
                              "            return stage(f'p{i}_{label}', argv, "
                              'lease_out=lease_root)\n'
                              "        initialization = out / 'phases' / "
                              "f'p{i}_initialize_input.json'\n"
                              "        initialize_body = dict(repo=b['repo'], "
                              "materializer=b['materializer'], output=str(profile), profile=i, "
                              "reference=b['references'][str(i)])\n"
                              '        if reference_reuse is not None:\n'
                              '            '
                              "initialize_body.update(reference_data_reuse=b['reference_data_reuse'], "
                              'reference_reuse_context=reference_reuse_context, '
                              'reference_reuse_source_pin=reference_reuse_source_pin)\n'
                              '        save(initialization, initialize_body)\n'
                              "        stage(f'p{i}_initialize', [b['python'], '-B', str(D / "
                              "'provider_from_frozen.py'), '--initialize-binding', "
                              "str(initialization), '--sha256', sha(initialization)], 120, "
                              'lease_out=lease_root)\n'
                              "        material.prepare(b['repo'], b['materializer'], profile, i, "
                              "runtime['wrapper'], b['payload'], b['references'][str(i)], "
                              "provider_stage, pins, p0_provider_reuse=b.get('p0_provider_reuse') "
                              'if i == 0 else None)\n'
                              "        stage(f'p{i}_connect', [b['python'], '-B', str(D / "
                              "'connect_owned.py'), '--existing-output', str(profile), "
                              "'--profile', str(i), *identity_args], 120, lease_out=lease_root)\n"
                              '        generated = json.loads((profile / '
                              "'CONSUMER_ARGV.json').read_text())['consumer_argv']\n"
                              '        generated, outer_seconds = execution_command(generated, b, '
                              'admission, i)\n'
                              '        if reference_reuse is not None:\n'
                              '            verify_reference_with_deadline(b, reference_reuse, '
                              'profile, i, reference_reuse_context)\n'
                              "        dut_outer = stage(f'p{i}_dut', generated, outer_seconds, "
                              'accepted=(1, 2), lease_out=lease_root)\n'
                              '        if reference_reuse is not None:\n'
                              '            verify_reference_with_deadline(b, reference_reuse, '
                              'profile, i, reference_reuse_context)\n'
                              "        bundle = profile / 'runtime_bundle.v3.json'\n"
                              '        bundle_doc = json.loads(bundle.read_text())\n'
                              '        runtime_sha = '
                              "bundle_doc['profiles'][0]['runtime']['sha256']\n"
                              "        diagnostic = dut_evidence.verify(profile / 'dut_result', i, "
                              "sha(manifest), sha(bundle), binary['sha256'], runtime_sha, "
                              "material.pin(out / 'runs' / f'p{i}_dut' / 'RESULT.json'))\n"
                              '        if cloud is not None:\n'
                              '            report = json.loads((profile / '
                              "'dut_result/RESULT.json').read_text())\n"
                              "            need(report.get('executor_identity') == cloud and "
                              "report.get('builder_handoff_sha256') == "
                              "b['builder_handoff']['sha256'], 'actual executor report not builder "
                              "identity')\n"
                              "            if b.get('executor_adaptation') is not None:\n"
                              "                need(report.get('executor_adaptation_sha256') == "
                              "b['executor_adaptation']['sha256'] and "
                              "report.get('workspace_loader_sha256') == "
                              "b['workspace_loader']['sha256'], 'actual executor adapter/loader "
                              "provenance')\n"
                              "        if admission['mode'] in (execution_mode.FULL, "
                              'execution_mode.STAGE):\n'
                              '            report = json.loads((profile / '
                              "'dut_result/RESULT.json').read_text())\n"
                              "            actual = report['execution_admission']\n"
                              "            need(actual['execution_mode'] == admission['mode'] and "
                              "actual['reviewed_budget_sha256'] == "
                              "admission['reviewed_budget_sha256'], 'actual consumer full-mode "
                              "budget identity')\n"
                              "            scope = 'STAGE_COVERAGE_DIAGNOSTIC_NOT_FULL_ACCEPTANCE' "
                              "if admission['mode'] == execution_mode.STAGE else "
                              "'FULL_BLOCK_ACCEPTANCE_REQUIRED_TERMINAL_AND_REFERENCE'\n"
                              "            need(actual['scope'] == scope and "
                              "actual['outer_cleanup_proof_required'] is True, 'actual explicit "
                              "execution scope')\n"
                              "            if admission['mode'] == execution_mode.STAGE:\n"
                              "                need(actual.get('stage_budget_sha256') == "
                              "admission['reviewed_budget_sha256'], 'actual stage coverage budget "
                              "identity')\n"
                              '            expected_limits = '
                              "report_effective_limits(actual['original_limits'], b, admission, "
                              'i)\n'
                              "            need(actual['effective_limits'] == expected_limits, "
                              "'actual full watchdog limits')\n"
                              '        dut_records.append(diagnostic)\n'
                              "        save(out / f'PROFILE_{i}_DIAGNOSTIC.json', diagnostic)\n"
                              '        weights(b, i)']]}
def undo_reviewed_first_fault_delta(test,tree,relative):
 import copy
 for digest,new_text,old_text in REVIEWED_FIRST_FAULT_INVERSE[relative]:
  want=ast.parse(new_text).body;replacement=ast.parse(old_text).body
  test.assertEqual(hashlib.sha256(ast.dump(ast.Module(body=want,type_ignores=[]),include_attributes=False).encode()).hexdigest(),digest)
  count=0
  want_dump=[ast.dump(n,include_attributes=False)for n in want]
  def visit(node):
   nonlocal count
   for field,value in ast.iter_fields(node):
    if isinstance(value,list):
     i=0
     while i<=len(value)-len(want):
      if all(type(n)is type(w)for n,w in zip(value[i:i+len(want)],want)) and [ast.dump(n,include_attributes=False)for n in value[i:i+len(want)]]==want_dump:
       value[i:i+len(want)]=copy.deepcopy(replacement);count+=1;i+=len(replacement)
      else:i+=1
     for item in value:
      if isinstance(item,ast.AST):visit(item)
    elif isinstance(value,ast.AST):visit(value)
  visit(tree);test.assertEqual(count,1,'exact reviewed inverse snippet matched once: '+digest)
 return tree

REVIEWED_STAGE_INVERSE = {'numeric/numeric_tail.py': [('bdcea0b9485bc538800ae32c592d6a6c4249b1a1913f741bbccbe3a540492a0c',
                              "for key in ('executor_adaptation', 'workspace_loader', "
                              "'model_candidate_review', 'stage_coverage_budget', 'p0_provider_reuse'):\n"
                              "    need(controller.get(key) == b.get(key), 'retained tail/controller "
                              "optional ' + key)",
                              "for key in ('executor_adaptation', 'workspace_loader', "
                              "'model_candidate_review'):\n"
                              "    need(controller.get(key) == b.get(key), 'retained tail/controller "
                              "optional ' + key)"),
                             ('bed00c36a34e5ccd3a72c41f9418cf2fe621c191907aa35e04166f1eb43760e6',
                              "need(admitted.get('stage_coverage_budget') == b.get('stage_coverage_budget'), "
                              "'tail exact approved stage coverage budget')\n"
                              "need(admitted.get('p0_provider_reuse') == b.get('p0_provider_reuse'), 'tail "
                              "exact approved P0 input reuse')\n"
                              "if b.get('p0_provider_reuse') is not None:\n"
                              "    need(b['execution_mode'] == execution_mode.STAGE and "
                              "b.get('model_candidate_review') is not None, 'P0 reuse only approved "
                              "candidate stage coverage')",
                              ''),
                             ('62abe71a79bdafe96809503b4f9bc5e99220c351dba8ab329721a93bf49e9b00',
                              'def execution_command(generated, b, admission, profile):\n'
                              "    need(generated[1] == str(D / 'consumer_owned.py'), 'explicit owned "
                              "consumer handoff')\n"
                              "    need(not any((flag in generated for flag in ('--execution-mode', "
                              "'--calibration-wall-seconds', '--full-block-budget', "
                              "'--full-block-budget-sha256', '--stage-coverage-budget', "
                              "'--stage-coverage-budget-sha256'))), 'no stale or duplicate execution mode "
                              "arguments')\n"
                              "    argv = list(generated) + ['--execution-mode', admission['mode']]\n"
                              "    if admission['mode'] == execution_mode.CALIBRATION:\n"
                              "        argv += ['--calibration-wall-seconds', "
                              "str(admission['profile_seconds'][str(profile)])]\n"
                              "    elif admission['mode'] == execution_mode.STAGE:\n"
                              "        need(b.get('execution_context') == 'CLOUD_EXECUTOR_V1' and "
                              "b.get('full_block_budget') is None, 'stage coverage is cloud-only, not full "
                              "acceptance')\n"
                              "        budget = b['stage_coverage_budget']\n"
                              "        argv += ['--stage-coverage-budget', budget['path'], "
                              "'--stage-coverage-budget-sha256', budget['sha256']]\n"
                              '    else:\n'
                              "        need(admission['mode'] == execution_mode.FULL, 'explicit execution "
                              "mode')\n"
                              "        budget = b['full_block_budget']\n"
                              "        argv += ['--full-block-budget', budget['path'], "
                              "'--full-block-budget-sha256', budget['sha256']]\n"
                              "    if b.get('execution_context') == 'CLOUD_EXECUTOR_V1':\n"
                              "        invocation = b['controller_binding']\n"
                              '        material.checked(invocation)\n'
                              "        flags = ('--cloud-binding', '--cloud-binding-sha256')\n"
                              '        if any((flag in argv for flag in flags)):\n'
                              "            need(all((argv.count(flag) == 1 for flag in flags)), 'exact one "
                              "paired generated cloud invocation')\n"
                              '            need(all((argv.index(flag) + 1 < len(argv) for flag in flags)), '
                              "'generated cloud invocation values')\n"
                              "            need(argv[argv.index(flags[0]) + 1] == invocation['path'] and "
                              "argv[argv.index(flags[1]) + 1] == invocation['sha256'], 'generated cloud "
                              "invocation unchanged')\n"
                              '        else:\n'
                              "            argv += ['--cloud-binding', invocation['path'], "
                              "'--cloud-binding-sha256', invocation['sha256']]\n"
                              "    return (argv, admission['profile_seconds'][str(profile)] + 30)\n"
                              'def mode_budget_fields(admission):\n'
                              "    if admission['mode'] == execution_mode.STAGE:\n"
                              '        return dict(full_budget_sha256=None, '
                              "stage_budget_sha256=admission['reviewed_budget_sha256'])\n"
                              "    need(admission['mode'] in (execution_mode.CALIBRATION, "
                              "execution_mode.FULL), 'explicit numeric execution mode')\n"
                              "    return dict(full_budget_sha256=admission['reviewed_budget_sha256'])",
                              'def execution_command(generated, b, admission, profile):\n'
                              "    need(generated[1] == str(D / 'consumer_owned.py'), 'explicit owned "
                              "consumer handoff')\n"
                              "    need(not any((flag in generated for flag in ('--execution-mode', "
                              "'--calibration-wall-seconds', '--full-block-budget', "
                              "'--full-block-budget-sha256'))), 'no stale or duplicate execution mode "
                              "arguments')\n"
                              "    argv = list(generated) + ['--execution-mode', admission['mode']]\n"
                              "    if admission['mode'] == execution_mode.CALIBRATION:\n"
                              "        argv += ['--calibration-wall-seconds', "
                              "str(admission['profile_seconds'][str(profile)])]\n"
                              '    else:\n'
                              "        need(admission['mode'] == execution_mode.FULL, 'explicit execution "
                              "mode')\n"
                              "        budget = b['full_block_budget']\n"
                              "        argv += ['--full-block-budget', budget['path'], "
                              "'--full-block-budget-sha256', budget['sha256']]\n"
                              "    if b.get('execution_context') == 'CLOUD_EXECUTOR_V1':\n"
                              "        invocation = b['controller_binding']\n"
                              '        material.checked(invocation)\n'
                              "        flags = ('--cloud-binding', '--cloud-binding-sha256')\n"
                              '        if any((flag in argv for flag in flags)):\n'
                              "            need(all((argv.count(flag) == 1 for flag in flags)), 'exact one "
                              "paired generated cloud invocation')\n"
                              '            need(all((argv.index(flag) + 1 < len(argv) for flag in flags)), '
                              "'generated cloud invocation values')\n"
                              "            need(argv[argv.index(flags[0]) + 1] == invocation['path'] and "
                              "argv[argv.index(flags[1]) + 1] == invocation['sha256'], 'generated cloud "
                              "invocation unchanged')\n"
                              '        else:\n'
                              "            argv += ['--cloud-binding', invocation['path'], "
                              "'--cloud-binding-sha256', invocation['sha256']]\n"
                              "    return (argv, admission['profile_seconds'][str(profile)] + 30)"),
                             ('14c45709306421c7eb9c1d7586bf2f0a7d73e60bbbbc44659fe65c77307a0667',
                              "save(out / 'REGISTERED_FIVE.json', "
                              "dict(execution_policy=profile_policy.checked(b), profiles=b['profiles'], "
                              "tokens=128, execution_mode=admission['mode'], "
                              "profile_seconds=admission['profile_seconds'], "
                              '**mode_budget_fields(admission), '
                              "scope='CHISEL_EMITTED_SV_SIMULATION_NOT_FINAL_RTL', numeric_pass=False))",
                              "save(out / 'REGISTERED_FIVE.json', "
                              "dict(execution_policy=profile_policy.checked(b), profiles=b['profiles'], "
                              "tokens=128, execution_mode=admission['mode'], "
                              "profile_seconds=admission['profile_seconds'], "
                              "full_budget_sha256=admission['reviewed_budget_sha256'], "
                              "scope='CHISEL_EMITTED_SV_SIMULATION_NOT_FINAL_RTL', numeric_pass=False))"),
                             ('248fbf4be67bf4368a057bbf852337fd07575088a5c54d838fe4f402557e539a',
                              "material.prepare(b['repo'], b['materializer'], profile, i, "
                              "runtime['wrapper'], b['payload'], b['references'][str(i)], provider_stage, "
                              "pins, p0_provider_reuse=b.get('p0_provider_reuse') if i == 0 else None)",
                              "material.prepare(b['repo'], b['materializer'], profile, i, "
                              "runtime['wrapper'], b['payload'], b['references'][str(i)], provider_stage, "
                              'pins)'),
                             ('11da7ba6b6bc4260b1e29ff4c005dfa915a4fffea63b4a69b7f7c23ee5c30b04',
                              "if admission['mode'] in (execution_mode.FULL, execution_mode.STAGE):\n"
                              "    report = json.loads((profile / 'dut_result/RESULT.json').read_text())\n"
                              "    actual = report['execution_admission']\n"
                              "    need(actual['execution_mode'] == admission['mode'] and "
                              "actual['reviewed_budget_sha256'] == admission['reviewed_budget_sha256'], "
                              "'actual consumer full-mode budget identity')\n"
                              "    scope = 'STAGE_COVERAGE_DIAGNOSTIC_NOT_FULL_ACCEPTANCE' if "
                              "admission['mode'] == execution_mode.STAGE else "
                              "'FULL_BLOCK_ACCEPTANCE_REQUIRED_TERMINAL_AND_REFERENCE'\n"
                              "    need(actual['scope'] == scope and actual['outer_cleanup_proof_required'] "
                              "is True, 'actual explicit execution scope')\n"
                              "    if admission['mode'] == execution_mode.STAGE:\n"
                              "        need(actual.get('stage_budget_sha256') == "
                              "admission['reviewed_budget_sha256'], 'actual stage coverage budget "
                              "identity')\n"
                              "    expected_limits = report_effective_limits(actual['original_limits'], b, "
                              'admission, i)\n'
                              "    need(actual['effective_limits'] == expected_limits, 'actual full watchdog "
                              "limits')",
                              "if admission['mode'] == execution_mode.FULL:\n"
                              "    report = json.loads((profile / 'dut_result/RESULT.json').read_text())\n"
                              "    actual = report['execution_admission']\n"
                              "    need(actual['execution_mode'] == admission['mode'] and "
                              "actual['reviewed_budget_sha256'] == admission['reviewed_budget_sha256'], "
                              "'actual consumer full-mode budget identity')\n"
                              "    need(actual['scope'] == "
                              "'FULL_BLOCK_ACCEPTANCE_REQUIRED_TERMINAL_AND_REFERENCE' and "
                              "actual['outer_cleanup_proof_required'] is True, 'actual full execution "
                              "scope')\n"
                              "    expected_limits = report_effective_limits(actual['original_limits'], b, "
                              'admission, i)\n'
                              "    need(actual['effective_limits'] == expected_limits, 'actual full watchdog "
                              "limits')"),
                             ('7ab78476782ee6a7a55c1fbfe868d9f131a7d019fb7a45a3e086710e4c11b930',
                              "save(out / 'RESULT.json', dict(execution_mode=admission['mode'], "
                              '**mode_budget_fields(admission), qualification=qualification, '
                              "execution_policy=profile_policy.checked(b), status=qualification['status'], "
                              "scope='CHISEL_GENERATED_SIMULATION_BACKEND_NOT_FINAL_RTL', stages=allstage, "
                              "profiles=b['profiles'], actual_dut_reports=dut_records, "
                              "numerical_pass=qualification['numerical_pass'], "
                              "moe_contract='ORIGINAL_TORCH_TOPK_PENDING_SMALL_ID_ACCEPTANCE', "
                              'uploaded_payloads=False))',
                              "save(out / 'RESULT.json', dict(execution_mode=admission['mode'], "
                              "full_budget_sha256=admission['reviewed_budget_sha256'], "
                              'qualification=qualification, execution_policy=profile_policy.checked(b), '
                              "status=qualification['status'], "
                              "scope='CHISEL_GENERATED_SIMULATION_BACKEND_NOT_FINAL_RTL', stages=allstage, "
                              "profiles=b['profiles'], actual_dut_reports=dut_records, "
                              "numerical_pass=qualification['numerical_pass'], "
                              "moe_contract='ORIGINAL_TORCH_TOPK_PENDING_SMALL_ID_ACCEPTANCE', "
                              'uploaded_payloads=False))')]}

# Exact inverse of the reviewed stage-coverage / P0 data-only additions.
# Mandatory unique full-AST snippet matches; original historical whole-AST hashes
# below remain unchanged. No arbitrary mode branch or dependency gate is skipped.
# Reference data-only delta: restore exact 82bafa AST before the prior reviewed inverse.
REVIEWED_REFERENCE_INVERSE = {'numeric/numeric_tail.py': [('ff7ac986fb69d6c04a1e20365c402d0823a056f0c4c5c3d01b69e40972a6ba2a',
                              "for key in ('executor_adaptation', 'workspace_loader', "
                              "'model_candidate_review', 'stage_coverage_budget', 'p0_provider_reuse', "
                              "'reference_data_reuse', 'aggregate_tree_cap_bytes'):\n"
                              "    need(controller.get(key) == b.get(key), 'retained tail/controller "
                              "optional ' + key)",
                              "for key in ('executor_adaptation', 'workspace_loader', "
                              "'model_candidate_review', 'stage_coverage_budget', 'p0_provider_reuse'):\n"
                              "    need(controller.get(key) == b.get(key), 'retained tail/controller "
                              "optional ' + key)"),
                             ('f335c3a3d68bcc37f034a8b2cccfcff13c899b44a5aa2e05f4bf022913265cd2',
                              "need(admitted.get('reference_data_reuse') == b.get('reference_data_reuse'), "
                              "'tail exact approved reference reuse')\n"
                              "need(b['tree_cap'] == admitted.get('aggregate_tree_cap_bytes', "
                              "live_budget.TREE_CAP), 'tail exact approved aggregate tree cap')\n"
                              "if b.get('reference_data_reuse') is not None:\n"
                              "    need(b['execution_mode'] == execution_mode.STAGE and "
                              "b.get('model_candidate_review') is not None, 'reference reuse only approved "
                              "candidate stage coverage')\n"
                              "if b.get('p0_provider_reuse') is not None:\n"
                              "    need(b['execution_mode'] == execution_mode.STAGE and "
                              "b.get('model_candidate_review') is not None, 'P0 reuse only approved "
                              "candidate stage coverage')",
                              "if b.get('p0_provider_reuse') is not None:\n"
                              "    need(b['execution_mode'] == execution_mode.STAGE and "
                              "b.get('model_candidate_review') is not None, 'P0 reuse only approved "
                              "candidate stage coverage')"),
                             ('19116881868d986c6fed893e53f49280c6736435da7813c791f06fc1ebade015',
                              'def verify_reference_with_deadline(b, helper, profile, i, context):\n'
                              "    need(0 <= time.monotonic() - b['job_started_monotonic'] <= "
                              "b['job_budget_seconds'], 'reference verification original job deadline')\n"
                              "    result = helper.verify_materialized(b['references'][str(i)], profile, i, "
                              "b['reference_data_reuse'], context)\n"
                              "    need(0 <= time.monotonic() - b['job_started_monotonic'] <= "
                              "b['job_budget_seconds'], 'reference verification exceeded original job "
                              "deadline')\n"
                              '    return result',
                              ''),
                             ('f8e3f7ae3c34b699d8fb1cf52f3a910a759af807eee7e774d93bf9eb603263dc',
                              "if b.get('reference_data_reuse') is None:\n"
                              "    need(b['tree_cap'] == live_budget.TREE_CAP, 'unchanged aggregate tree "
                              "cap')\n"
                              'else:\n'
                              "    need(cloud is not None and b['execution_mode'] == execution_mode.STAGE "
                              "and (b['tree_cap'] == 12037043872), 'exact reference-data-only tree "
                              "reduction')",
                              "need(b['tree_cap'] == 12081306272, 'unchanged aggregate tree cap')"),
                             ('201b58c658b66b8c1185628dcb13b51ab3de16464225a0a32aa1275f6335ec07',
                              'reference_reuse = None\n'
                              'reference_reuse_context = None\n'
                              'reference_reuse_source_pin = None\n'
                              "if b.get('reference_data_reuse') is not None:\n"
                              "    reference_reuse = module('tail_reference_data_reuse', D / "
                              "'reference_data_reuse.py', pins)\n"
                              "    reference_reuse_context = {key: b[key] for key in ('repo', "
                              "'artifact_manifest', 'retained_materials')}\n"
                              "    reference_reuse_source_pin = material.pin(D / 'reference_data_reuse.py')\n"
                              '    verified_reference = '
                              "reference_reuse.verify_metadata(b['reference_data_reuse'], "
                              'reference_reuse_context)\n'
                              "    need(verified_reference['tree_cap'] == b['tree_cap'], 'actual reference "
                              "reuse tree cap')\n"
                              '    need(all((any((P(p).resolve().is_relative_to(r) for r in roots)) for p in '
                              "verified_reference['roots'])), 'all reference data and evidence watched')\n"
                              "common = frozen['common']",
                              "common = frozen['common']"),
                             ('3a5a60397c12265515b40e77e449f94a146a7b5ff60c2d565ee02fa5271c504e',
                              'body = dict(argv=list(map(str, argv)), pins=pins, '
                              "owned_roots=b['owned_roots'], extra_bytes=b['phase_extra_bytes'], "
                              "seconds=seconds, job_started=b['job_started_monotonic'], "
                              "job_budget_seconds=b['job_budget_seconds'] if cloud is not None else 21000, "
                              "write_file_bytes=128 << 20, tree_cap=b['tree_cap'], environment=e, "
                              'cache_root=str(cache_root), admission_output=str(run_dir / '
                              "'LIVE_ADMISSION.json'))",
                              'body = dict(argv=list(map(str, argv)), pins=pins, '
                              "owned_roots=b['owned_roots'], extra_bytes=b['phase_extra_bytes'], "
                              "seconds=seconds, job_started=b['job_started_monotonic'], "
                              "job_budget_seconds=b['job_budget_seconds'] if cloud is not None else 21000, "
                              'write_file_bytes=128 << 20, environment=e, cache_root=str(cache_root), '
                              "admission_output=str(run_dir / 'LIVE_ADMISSION.json'))"),
                             ('38c41794e611a978593454d007b5a4a75a109ba1af12a9dd6a993fec91d907b2',
                              "initialize_body = dict(repo=b['repo'], materializer=b['materializer'], "
                              "output=str(profile), profile=i, reference=b['references'][str(i)])\n"
                              'if reference_reuse is not None:\n'
                              "    initialize_body.update(reference_data_reuse=b['reference_data_reuse'], "
                              'reference_reuse_context=reference_reuse_context, '
                              'reference_reuse_source_pin=reference_reuse_source_pin)\n'
                              'save(initialization, initialize_body)',
                              "save(initialization, dict(repo=b['repo'], materializer=b['materializer'], "
                              "output=str(profile), profile=i, reference=b['references'][str(i)]))"),
                             ('eed756aaaf62d528bf183c6399782a41e1656d60f073eb82f23092fdae5b2508',
                              'if reference_reuse is not None:\n'
                              '    verify_reference_with_deadline(b, reference_reuse, profile, i, '
                              'reference_reuse_context)\n'
                              "dut_outer = stage(f'p{i}_dut', generated, outer_seconds, accepted=(1, 2), "
                              'lease_out=lease_root)',
                              "dut_outer = stage(f'p{i}_dut', generated, outer_seconds, accepted=(1, 2), "
                              'lease_out=lease_root)'),
                             ('aef4df3c3e76a5bee55665609e38bc90cc45f8ccb1c7cfeb60ddf9903d2925e0',
                              'if reference_reuse is not None:\n'
                              '    verify_reference_with_deadline(b, reference_reuse, profile, i, '
                              'reference_reuse_context)\n'
                              "bundle = profile / 'runtime_bundle.v3.json'",
                              "bundle = profile / 'runtime_bundle.v3.json'")]}
def undo_reviewed_reference_delta(test,tree,relative):
 tree=undo_reviewed_first_fault_delta(test,tree,relative)
 import copy
 for digest,new_text,old_text in REVIEWED_REFERENCE_INVERSE[relative]:
  want=ast.parse(new_text).body;replacement=ast.parse(old_text).body
  test.assertEqual(hashlib.sha256(ast.dump(ast.Module(body=want,type_ignores=[]),include_attributes=False).encode()).hexdigest(),digest)
  count=0
  def visit(node):
   nonlocal count
   for field,value in ast.iter_fields(node):
    if isinstance(value,list):
     i=0
     while i<=len(value)-len(want):
      if [ast.dump(n,include_attributes=False)for n in value[i:i+len(want)]]==[ast.dump(n,include_attributes=False)for n in want]:
       value[i:i+len(want)]=copy.deepcopy(replacement);count+=1;i+=len(replacement)
      else:i+=1
     for item in value:
      if isinstance(item,ast.AST):visit(item)
    elif isinstance(value,ast.AST):visit(value)
  visit(tree);test.assertEqual(count,1,'exact reviewed inverse snippet matched once: '+digest)
 return tree

def undo_reviewed_stage_delta(test,tree,relative):
 tree=undo_reviewed_reference_delta(test,tree,relative)
 import copy
 for digest,new_text,old_text in REVIEWED_STAGE_INVERSE[relative]:
  want=ast.parse(new_text).body;replacement=ast.parse(old_text).body
  test.assertEqual(hashlib.sha256(ast.dump(ast.Module(body=want,type_ignores=[]),include_attributes=False).encode()).hexdigest(),digest)
  count=0
  def visit(node):
   nonlocal count
   for field,value in ast.iter_fields(node):
    if isinstance(value,list):
     i=0
     while i<=len(value)-len(want):
      if [ast.dump(n,include_attributes=False)for n in value[i:i+len(want)]]==[ast.dump(n,include_attributes=False)for n in want]:
       value[i:i+len(want)]=copy.deepcopy(replacement);count+=1;i+=len(replacement)
      else:i+=1
     for item in value:
      if isinstance(item,ast.AST):visit(item)
    elif isinstance(value,ast.AST):visit(value)
  visit(tree);test.assertEqual(count,1,'exact reviewed inverse snippet matched once: '+digest)
 return tree

class Held(Exception):pass

def receipt():
 return dict(argv=['synthetic'],caps={},cleanup_proof=None,elapsed_seconds=0.1,errors=['ValueError: locked memory gate'],limitations=[],native_exit=None,observed_cpu_seconds=0,observed_peak_rss=0,observed_processes=[],peak_file_bytes=0,peak_tree_bytes=0,reader_join_barrier={'complete':True,'alive':False,'reader_finally_done':False},scope='ORIGINAL_PROCESS_GROUP_AND_OBSERVED_DESCENDANTS_ONLY',status='FAIL_OR_INCOMPLETE',supervisor_cpu_scope='synthetic',supervisor_cpu_seconds=0.1,worker_started=False)

class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=P(self.tmp.name);self.run=self.root/'absent';self.supervisor=self.root/'supervisor.py';self.supervisor.write_text('synthetic');self.marker=self.root/'HOLD.json'
 def held(self,r,run=None,source=None):
  with patch.object(signal,'pause',side_effect=Held),patch.dict(ns,sha=lambda p:ns['PRELAUNCH_SUPERVISOR_SHA']):
   with self.assertRaises(Held):ns['require_cleanup'](r,self.marker,self.run if run is None else run,self.supervisor if source is None else source)
  self.assertEqual(json.loads(self.marker.read_text())['status'],'HOLD_PARENT_LEASE_NO_CONTINUATION');self.marker.unlink()
  self.assertFalse(self.marker.with_name('PRELAUNCH_REJECTED_'+self.marker.name).exists())
 def test_exact_prelaunch_three_errors(self):
  for error in ns['PRELAUNCH_ERRORS']:
   r=receipt();r['errors']=[error]
   with patch.dict(ns,sha=lambda p:ns['PRELAUNCH_SUPERVISOR_SHA']):
    with self.assertRaisesRegex(ValueError,'before worker launch; INCOMPLETE'):ns['require_cleanup'](r,self.marker,self.run,self.supervisor)
   marker=self.marker.with_name('PRELAUNCH_REJECTED_'+self.marker.name);self.assertFalse(self.marker.exists());self.assertFalse(self.run.exists());self.assertFalse(json.loads(marker.read_text())['numerical_pass']);marker.unlink()
 def test_unknown_or_started_evidence_holds(self):
  changes=[{'worker_started':0},{'worker_started':True},{'native_exit':0},{'cleanup_proof':{}},{'observed_processes':[{'pid':1}]},{'observed_processes':()}, {'owner_identity':None},{'log_capture':None},{'errors':['ValueError: leader identity mismatch']},{'errors':['ValueError: locked memory gate','extra']},{'observed_peak_rss':1},{'reader_join_barrier':{'complete':True,'alive':False,'reader_finally_done':True}},{'reader_join_barrier':{'complete':1,'alive':0,'reader_finally_done':False}},{'unknown_process_identity':1}]
  for delta in changes:
   with self.subTest(delta=delta):r=receipt();r.update(delta);self.held(r)
 def test_existing_run_and_dangling_symlink_hold(self):
  self.run.mkdir();self.held(receipt());self.run.rmdir();self.run.symlink_to(self.root/'missing');self.held(receipt())
 def test_post_popen_pre_flag_failure_holds(self):
  self.run.mkdir();(self.run/'frontend.log.gz').write_bytes(b'')
  r=receipt();r['errors']=['ValueError: leader verification'];self.held(r)
 def test_missing_arguments_or_bad_source_hold(self):
  with patch.object(signal,'pause',side_effect=Held):
   with self.assertRaises(Held):ns['require_cleanup'](receipt(),self.marker)
  self.marker.unlink()
  with patch.object(signal,'pause',side_effect=Held):
   with self.assertRaises(Held):ns['require_cleanup'](receipt(),self.marker,self.run,self.supervisor)
 def test_complete_unchanged(self):
  r={'cleanup_proof':{'status':'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'},'log_capture':{'pipe_eof_observed':True,'gzip_finalized':True}}
  ns['require_cleanup'](r,self.marker);self.assertFalse(self.marker.exists())
 def test_actual_retained_return_and_source_order(self):
  if not os.environ.get('ACTUAL_RETURN')or not os.environ.get('SUPERVISOR_SOURCE'):self.skipTest('optional actual read-only evidence paths not supplied')
  actual=P(os.environ['ACTUAL_RETURN']);supervisor=P(os.environ['SUPERVISOR_SOURCE'])
  self.assertEqual(hashlib.sha256(actual.read_bytes()).hexdigest(),'c89287a9aa298fc602d172b6cab4b6ff2653730989fc4517250d339ad3495fa9')
  r=json.loads(actual.read_text());actual_run=actual.parent.parent/'runs'/actual.name.removesuffix('_SUPERVISOR_RETURN.json');self.assertTrue(ns['prelaunch_rejection'](r,actual_run,supervisor));self.assertTrue(ns['prelaunch_rejection'](r,self.run,supervisor))
  text=supervisor.read_text();self.assertEqual(ns['sha'](supervisor),ns['PRELAUNCH_SUPERVISOR_SHA'])
  self.assertLess(text.index("'locked memory gate'"),text.index('run.mkdir()'));self.assertLess(text.index("'locked disk gate'"),text.index('run.mkdir()'));self.assertLess(text.index("'prelaunch work deadline'"),text.index('run.mkdir()'));self.assertLess(text.index('run.mkdir()'),text.index('p=subprocess.Popen('));self.assertLess(text.index('p=subprocess.Popen('),text.index("report['worker_started']=True"))
 def test_full_prefill_inverse_rejects_foreign_sibling(self):
  bad=undo_reviewed_v3_delta(self,undo_reviewed_finite_log_delta(self,undo_reviewed_aggregate_cap_delta(self,source,'numeric/numeric_tail.py'),'numeric/numeric_tail.py'),'numeric/numeric_tail.py');run=next(n for n in bad.body if isinstance(n,ast.FunctionDef)and n.name=='run');run.body.append(ast.parse("foreign_unreviewed_change = True").body[0])
  with self.assertRaisesRegex(AssertionError,'reviewed full-prefill function bytes run'):undo_reviewed_full_prefill_delta(self,bad)
 def test_all_other_production_ast_unchanged(self):
  self.check_original_ast(undo_reviewed_v3_delta(self,undo_reviewed_finite_log_delta(self,undo_reviewed_aggregate_cap_delta(self,source,'numeric/numeric_tail.py'),'numeric/numeric_tail.py'),'numeric/numeric_tail.py'))
 def check_original_ast(self,tree):
  t=undo_reviewed_stage_delta(self,undo_reviewed_full_prefill_delta(self,copy.deepcopy(tree)),'numeric/numeric_tail.py')
  t.body=[n for n in t.body if not(isinstance(n,ast.FunctionDef)and n.name=='prelaunch_rejection')and not(isinstance(n,ast.Assign)and any(isinstance(x,ast.Name)and x.id.startswith('PRELAUNCH_')for x in n.targets))]
  old=ast.parse("def require_cleanup(r,marker):\n if not complete(r):\n  save(marker,dict(status='HOLD_PARENT_LEASE_NO_CONTINUATION'))\n  while True:signal.pause()\n").body[0]
  t.body=[old if isinstance(n,ast.FunctionDef)and n.name=='require_cleanup'else n for n in t.body]
  for n in ast.walk(t):
   if isinstance(n,ast.Call)and isinstance(n.func,ast.Name)and n.func.id=='require_cleanup':n.args=n.args[:2]
  # Undo ONLY exact independently reviewed candidate additions. Each match is
  # mandatory once; every remaining AST node is still checked by the old hash.
  def replace_statements(new_text,old_text):
   want=ast.parse(new_text).body;replacement=ast.parse(old_text).body;count=0
   def visit(node):
    nonlocal count
    for field,value in ast.iter_fields(node):
     if isinstance(value,list):
      i=0
      while i<=len(value)-len(want):
       if list(map(lambda n:ast.dump(n,include_attributes=False),value[i:i+len(want)]))==list(map(lambda n:ast.dump(n,include_attributes=False),want)):
        value[i:i+len(want)]=copy.deepcopy(replacement);count+=1;i+=len(replacement)
       else:i+=1
      for item in value:
       if isinstance(item,ast.AST):visit(item)
     elif isinstance(value,ast.AST):visit(value)
   visit(t);self.assertEqual(count,1,new_text)
  replace_statements("if b.get('model_candidate_review')is not None:need(controller['source_pins']==b['source_pins'],'candidate tail/controller exact source catalog')",'')
  replace_statements("need(admitted.get('model_candidate_review')==b.get('model_candidate_review'),'tail exact approved candidate review')\nif b.get('model_candidate_review')is not None:module('tail_model_candidate',D/'candidate_admission.py',b['pins']).verify(b['model_candidate_review'],b)",'')
  replace_statements("""
candidate=frozen['schema']=='MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1'
proof=module('split_build_proof',D/('candidate_artifact_handoff.py'if candidate else'artifact_handoff.py'),pins)
kwargs=dict(executor_adaptation=b.get('executor_adaptation'))
if candidate:kwargs.update(model_candidate_review=b.get('model_candidate_review'),current_source_pins_pin=b['source_pins'],repo=b['repo'])
proof.verify(b['builder_handoff']['path'],b['builder_handoff']['sha256'],manifest,sha(manifest),frozen,cloud,**kwargs)
""","""
proof=module('split_build_proof',D/'artifact_handoff.py',pins)
proof.verify(b['builder_handoff']['path'],b['builder_handoff']['sha256'],manifest,sha(manifest),frozen,cloud,executor_adaptation=b.get('executor_adaptation'))
""")
  pairs=[("('executor_adaptation','workspace_loader','model_candidate_review')","('executor_adaptation','workspace_loader')"),("('DATA_REFERENCE_ONLY_NOT_NUMERICAL_ABI_OR_RUNTIME_PASS'if b.get('model_candidate_review')is not None else'REVALIDATED_DATA_AND_SOFTWARE_REFERENCES_NOT_RUNTIME_OR_DUT')","'REVALIDATED_DATA_AND_SOFTWARE_REFERENCES_NOT_RUNTIME_OR_DUT'")]
  for new_text,old_text in pairs:
   new=ast.parse(new_text,mode='eval').body;old=ast.parse(old_text,mode='eval').body;hits=[]
   class Normalize(ast.NodeTransformer):
    def visit(self,node):
     if ast.dump(node,include_attributes=False)==ast.dump(new,include_attributes=False):hits.append(True);return copy.deepcopy(old)
     return super().visit(node)
   t=Normalize().visit(t);self.assertEqual(len(hits),1,new_text)
  self.assertEqual(hashlib.sha256(ast.dump(t,include_attributes=False).encode()).hexdigest(),'d9dac3f15753fab0b3a137a9baee460061b0f15c9a3a6a8d777631793573d171')
 def test_actual_stage_passes_real_output_and_supervisor_source(self):
  calls=[n for n in ast.walk(source)if isinstance(n,ast.Call)and isinstance(n.func,ast.Name)and n.func.id=='require_cleanup']
  self.assertEqual(len(calls),1);self.assertEqual(ast.unparse(calls[0].args[2]),'run_dir');self.assertEqual(ast.unparse(calls[0].args[3]),'P(supervisor.__file__)')
class InverseNegativeTests(unittest.TestCase):
 def test_reviewed_delta_mutation_and_duplicate_rejected(self):
  for relative,rows in REVIEWED_STAGE_INVERSE.items():
   root=D.parent if D.name=='numeric'else D
   original=undo_reviewed_v3_delta(self,undo_reviewed_finite_log_delta(self,undo_reviewed_aggregate_cap_delta(self,ast.parse((root/relative).read_text()),relative),relative),relative)
   # An additional copy cannot silently disappear: unique match count must fail.
   duplicate=undo_reviewed_v3_delta(self,undo_reviewed_finite_log_delta(self,undo_reviewed_aggregate_cap_delta(self,ast.parse((root/relative).read_text()),relative),relative),relative);duplicate.body.extend(ast.parse(rows[0][1]).body)
   with self.subTest(relative=relative,case='duplicate'),self.assertRaises(AssertionError):undo_reviewed_stage_delta(self,duplicate,relative)
   # Mutating the stage discriminator anywhere is not accepted as the reviewed delta.
   hit=False
   for n in ast.walk(original):
    if isinstance(n,ast.Constant)and n.value=='STAGE_COVERAGE_DIAGNOSTIC':n.value='UNREVIEWED_STAGE_MODE';hit=True
   if not hit:
    for n in ast.walk(original):
     if isinstance(n,ast.Attribute)and n.attr=='STAGE':n.attr='UNREVIEWED_STAGE';hit=True
   self.assertTrue(hit)
   with self.subTest(relative=relative,case='changed gate'),self.assertRaises(AssertionError):undo_reviewed_stage_delta(self,original,relative)

class ReferenceInverseNegativeTests(unittest.TestCase):
 def test_reference_gate_mutation_and_duplicate_rejected(self):
  for relative,rows in REVIEWED_REFERENCE_INVERSE.items():
   root=D.parent if D.name=='numeric'else D
   original=undo_reviewed_v3_delta(self,undo_reviewed_finite_log_delta(self,undo_reviewed_aggregate_cap_delta(self,ast.parse((root/relative).read_text()),relative),relative),relative)
   duplicate=undo_reviewed_v3_delta(self,undo_reviewed_finite_log_delta(self,undo_reviewed_aggregate_cap_delta(self,ast.parse((root/relative).read_text()),relative),relative),relative);duplicate.body.extend(ast.parse(rows[0][1]).body)
   with self.subTest(relative=relative,case='duplicate'),self.assertRaises(AssertionError):undo_reviewed_reference_delta(self,duplicate,relative)
   hit=False
   for n in ast.walk(original):
    if isinstance(n,ast.Constant)and n.value=='reference_data_reuse':n.value='UNREVIEWED_REFERENCE_REUSE';hit=True
   self.assertTrue(hit)
   with self.subTest(relative=relative,case='changed gate'),self.assertRaises(AssertionError):undo_reviewed_reference_delta(self,original,relative)


class FirstFaultInverseNegativeTests(unittest.TestCase):
 def test_every_fixed_fragment_duplicate_rejected(self):
  for name,rows in REVIEWED_FIRST_FAULT_INVERSE.items():
   for _,text,_ in rows:
    fixture=ast.parse('\n'.join(row[1]for row in rows))
    fixture.body.extend(ast.parse(text).body)
    with self.subTest(name=name,fragment=text[:60]),self.assertRaises(AssertionError):undo_reviewed_first_fault_delta(self,fixture,name)
 def test_every_fixed_fragment_mutation_rejected(self):
  for name,rows in REVIEWED_FIRST_FAULT_INVERSE.items():
   for index,(_,text,_)in enumerate(rows):
    parts=[ast.parse(row[1]).body for row in rows]
    # Mutate one literal in this exact fragment; no production code runs.
    constants=[n for stmt in parts[index]for n in ast.walk(stmt)if isinstance(n,ast.Constant)and isinstance(n.value,str)]
    self.assertTrue(constants);constants[0].value='UNREVIEWED_FIRST_FAULT_TEST_MUTATION'
    fixture=ast.Module(body=[n for part in parts for n in part],type_ignores=[])
    with self.subTest(name=name,fragment=text[:60]),self.assertRaises(AssertionError):undo_reviewed_first_fault_delta(self,fixture,name)


class V3PrelaunchInverseTests(unittest.TestCase):
 def test_v3_restores_exact_frozen_v2_tail_ast(self):
  restored=undo_reviewed_v3_delta(self,undo_reviewed_finite_log_delta(self,undo_reviewed_aggregate_cap_delta(self,source,'numeric/numeric_tail.py'),'numeric/numeric_tail.py'),'numeric/numeric_tail.py')
  self.assertEqual(hashlib.sha256(ast.dump(restored,include_attributes=False).encode()).hexdigest(),PRE_V3_AST_SHA256)
 def test_each_v3_fragment_missing_mutated_or_duplicated_is_rejected(self):
  rows=REVIEWED_V3_INVERSE['numeric/numeric_tail.py']
  self.assertEqual([row[4]for row in rows],[20,19,18])
  for digest,new_text,old_digest,old_text,author_index in rows:
   want=ast.parse(new_text).body;want_dump=[ast.dump(n,include_attributes=False)for n in want]
   for case in ('missing','mutated','duplicate'):
    tree=undo_reviewed_finite_log_delta(self,undo_reviewed_aggregate_cap_delta(self,source,'numeric/numeric_tail.py'),'numeric/numeric_tail.py');hits=[]
    for parent in ast.walk(tree):
     for field,value in ast.iter_fields(parent):
      if isinstance(value,list):
       for i in range(len(value)-len(want)+1):
        if all(isinstance(n,ast.AST)for n in value[i:i+len(want)])and [ast.dump(n,include_attributes=False)for n in value[i:i+len(want)]]==want_dump:hits.append((value,i))
    self.assertEqual(len(hits),1);container,index=hits[0]
    if case=='missing':del container[index:index+len(want)]
    elif case=='duplicate':container[index:index]=copy.deepcopy(want)
    else:
     names=[n for node in container[index:index+len(want)]for n in ast.walk(node)if isinstance(n,ast.Name)]
     self.assertTrue(names);names[0].id='UNREVIEWED_V3_MUTATION'
    with self.subTest(author_index=author_index,case=case),self.assertRaisesRegex(AssertionError,'one exact reviewed V3 fragment: '+digest):undo_reviewed_v3_delta(self,tree,'numeric/numeric_tail.py')
 def test_unrelated_caller_delta_fails_original_baseline(self):
  tree=undo_reviewed_finite_log_delta(self,undo_reviewed_aggregate_cap_delta(self,source,'numeric/numeric_tail.py'),'numeric/numeric_tail.py');tree.body.extend(ast.parse('UNREVIEWED_V3_CALLER_DELTA = 1').body)
  before=ast.dump(tree,include_attributes=False);restored=undo_reviewed_v3_delta(self,tree,'numeric/numeric_tail.py')
  self.assertEqual(ast.dump(tree,include_attributes=False),before,'V3 inverse preserves its input')
  self.assertIn('UNREVIEWED_V3_CALLER_DELTA',ast.unparse(restored))
  with self.assertRaises(AssertionError)as caught:Tests().check_original_ast(restored)
  self.assertIn('d9dac3f15753fab0b3a137a9baee460061b0f15c9a3a6a8d777631793573d171',str(caught.exception),'original baseline hash is the rejection reason')
  self.assertNotIn('one exact reviewed V3 fragment',str(caught.exception))
  self.assertNotIn('reviewed full-prefill function bytes',str(caught.exception))


class FiniteLogInverseTests(unittest.TestCase):
 def test_finite_log_restores_exact_prior_v3_tail_ast(self):
  restored=undo_reviewed_finite_log_delta(self,undo_reviewed_aggregate_cap_delta(self,source,'numeric/numeric_tail.py'),'numeric/numeric_tail.py')
  self.assertEqual(hashlib.sha256(ast.dump(restored,include_attributes=False).encode()).hexdigest(),PRE_FINITE_LOG_AST_SHA256)
 def test_each_finite_fragment_missing_mutated_or_duplicated_rejected(self):
  import copy
  for digest,new_text,old_digest,old_text in REVIEWED_FINITE_LOG_INVERSE['numeric/numeric_tail.py']:
   want=ast.parse(new_text).body;want_dump=[ast.dump(n,include_attributes=False)for n in want]
   for case in ('missing','mutated','duplicate'):
    tree=undo_reviewed_aggregate_cap_delta(self,source,'numeric/numeric_tail.py');hits=[]
    for parent in ast.walk(tree):
     for field,value in ast.iter_fields(parent):
      if isinstance(value,list):
       for i in range(len(value)-len(want)+1):
        if all(isinstance(n,ast.AST)for n in value[i:i+len(want)])and [ast.dump(n,include_attributes=False)for n in value[i:i+len(want)]]==want_dump:hits.append((value,i))
    self.assertEqual(len(hits),1);container,index=hits[0]
    if case=='missing':del container[index:index+len(want)]
    elif case=='duplicate':container[index:index]=copy.deepcopy(want)
    else:
     names=[n for node in container[index:index+len(want)]for n in ast.walk(node)if isinstance(n,ast.Name)]
     self.assertTrue(names);names[0].id='UNREVIEWED_FINITE_LOG_MUTATION'
    with self.subTest(digest=digest,case=case),self.assertRaisesRegex(AssertionError,'one exact finite-log fragment: '+digest):undo_reviewed_finite_log_delta(self,tree,'numeric/numeric_tail.py')
 def test_unrelated_delta_reaches_original_historical_hash(self):
  import copy
  tree=undo_reviewed_aggregate_cap_delta(self,source,'numeric/numeric_tail.py');tree.body.extend(ast.parse('UNREVIEWED_FINITE_LOG_CALLER_DELTA = 1').body)
  before=ast.dump(tree,include_attributes=False);restored=undo_reviewed_finite_log_delta(self,tree,'numeric/numeric_tail.py')
  self.assertEqual(ast.dump(tree,include_attributes=False),before,'finite inverse preserves input')
  self.assertIn('UNREVIEWED_FINITE_LOG_CALLER_DELTA',ast.unparse(restored))
  with self.assertRaises(AssertionError)as caught:Tests().check_original_ast(undo_reviewed_v3_delta(self,restored,'numeric/numeric_tail.py'))
  self.assertIn('d9dac3f15753fab0b3a137a9baee460061b0f15c9a3a6a8d777631793573d171',str(caught.exception),'original historical hash is rejection reason')
  self.assertNotIn('one exact finite-log fragment',str(caught.exception))
  self.assertNotIn('one exact reviewed V3 fragment',str(caught.exception))


class AggregateCapInverseTests(unittest.TestCase):
 def test_aggregate_restores_exact_prior_source_ast(self):
  for relative,wanted in PRE_AGGREGATE_AST_SHA256.items():
   restored=undo_reviewed_aggregate_cap_delta(self,source,relative)
   with self.subTest(relative=relative):self.assertEqual(hashlib.sha256(ast.dump(restored,include_attributes=False).encode()).hexdigest(),wanted)
 def test_each_aggregate_fragment_missing_mutated_or_duplicated_rejected(self):
  import copy
  for relative,rows in REVIEWED_AGGREGATE_CAP_INVERSE.items():
   for digest,new_text,old_digest,old_text in rows:
    want=ast.parse(new_text).body;want_dump=[ast.dump(n,include_attributes=False)for n in want]
    for case in ('missing','mutated','duplicate'):
     tree=copy.deepcopy(source);hits=[]
     for parent in ast.walk(tree):
      for field,value in ast.iter_fields(parent):
       if isinstance(value,list):
        for i in range(len(value)-len(want)+1):
         if all(isinstance(n,ast.AST)for n in value[i:i+len(want)])and [ast.dump(n,include_attributes=False)for n in value[i:i+len(want)]]==want_dump:hits.append((value,i))
     self.assertEqual(len(hits),1);container,index=hits[0]
     if case=='missing':del container[index:index+len(want)]
     elif case=='duplicate':container[index:index]=copy.deepcopy(want)
     else:
      names=[n for node in container[index:index+len(want)]for n in ast.walk(node)if isinstance(n,ast.Name)]
      self.assertTrue(names);names[0].id='UNREVIEWED_AGGREGATE_MUTATION'
     with self.subTest(relative=relative,digest=digest,case=case),self.assertRaisesRegex(AssertionError,'one exact aggregate-cap fragment: '+digest):undo_reviewed_aggregate_cap_delta(self,tree,relative)
 def test_unrelated_delta_reaches_original_historical_hash(self):
  import copy
  for relative in PRE_AGGREGATE_AST_SHA256:
   tree=copy.deepcopy(source);tree.body.extend(ast.parse('UNREVIEWED_AGGREGATE_CALLER_DELTA = 1').body)
   before=ast.dump(tree,include_attributes=False);restored=undo_reviewed_aggregate_cap_delta(self,tree,relative)
   self.assertEqual(ast.dump(tree,include_attributes=False),before,'aggregate inverse preserves input')
   self.assertIn('UNREVIEWED_AGGREGATE_CALLER_DELTA',ast.unparse(restored))
   with self.subTest(relative=relative),self.assertRaises(AssertionError)as caught:Tests().check_original_ast(undo_reviewed_v3_delta(self,undo_reviewed_finite_log_delta(self,restored,relative),relative))
   self.assertIn('d9dac3f15753fab0b3a137a9baee460061b0f15c9a3a6a8d777631793573d171',str(caught.exception),'original historical hash is rejection reason')
   self.assertNotIn('one exact aggregate-cap fragment',str(caught.exception))
   self.assertNotIn('one exact finite-log fragment',str(caught.exception))
   self.assertNotIn('one exact reviewed V3 fragment',str(caught.exception))

if __name__=='__main__':unittest.main()
