"""Light file-only diagnostics; no census, job, supervisor or DUT execution."""
import ast,hashlib,importlib.util,json,pathlib,tempfile,unittest
import os
D=pathlib.Path(os.environ.get('FIRST_FAULT_LEGACY_TEST_SOURCE',str(pathlib.Path(__file__).resolve().parent))).resolve()
s=importlib.util.spec_from_file_location('disk_flow',D/'controller/cloud_flow.py');f=importlib.util.module_from_spec(s);s.loader.exec_module(f)
EXPECTED_BASE_AST='6007e2b7aa04308f9b4c51287ce7ce027da9f53348c4ac0a83f97b10e71c96e2'
REVIEWED_STAGE_INVERSE = {'controller/cloud_flow.py': [('ec28fb2ab41c8dc48e0a85a92172288f9b29736758e86ed7ae5e802effcec384',
                               "if mode in ('BOUNDED_CALIBRATION', 'STAGE_COVERAGE_DIAGNOSTIC'):\n"
                               '    return 2',
                               "if mode == 'BOUNDED_CALIBRATION':\n    return 2"),
                              ('f996f537187634ea5e4a0fe0ffc028e7e58b41181be65d18a118ab58b758f2bd',
                               'def verified_p0_provider_reuse(b, budget, candidate):\n'
                               "    if 'p0_provider_reuse' not in b:\n"
                               '        return None\n'
                               "    need(candidate and budget['execution_mode'] == "
                               "'STAGE_COVERAGE_DIAGNOSTIC', 'P0 data reuse only approved candidate stage "
                               "diagnostic')\n"
                               "    need(b['p0_provider_reuse'] == budget.get('p0_provider_reuse'), 'P0 "
                               "reuse equals independent approved pin')\n"
                               "    reuse_path = D.parent / 'numeric/p0_provider_data_reuse.py'\n"
                               "    need(b['pins'].get(str(reuse_path)) == sha(reuse_path), 'P0 pure data "
                               "reuse verifier source pin')\n"
                               "    reused = mod('actual_p0_provider_data_reuse', "
                               "reuse_path).verify_metadata(b['p0_provider_reuse'], b)\n"
                               "    need(reused['watch_scope'] == 'PURE_PROVIDER_AND_FINITE_EVIDENCE_V1' and "
                               "reused['roots'] == [reused['provider_root'], reused['evidence_root']], 'only "
                               "verified pure provider and finite evidence directories watched')\n"
                               '    return reused\n'
                               'def stage_budget_watch_coverage(b, roots):\n'
                               "    if b.get('execution_mode') != 'STAGE_COVERAGE_DIAGNOSTIC':\n"
                               '        return\n'
                               "    row = b['stage_coverage_budget']\n"
                               "    path = P(row['path'])\n"
                               "    need(pin(path) == row, 'stage budget immutable before watch admission')\n"
                               '    doc = json.loads(path.read_text())\n'
                               "    for evidence in doc['basis'].values():\n"
                               "        p = P(evidence['path'])\n"
                               '        need(p.is_absolute() and p == p.resolve() and '
                               "any((p.is_relative_to(P(root).resolve()) for root in roots)), 'stage "
                               "calibration/review metadata must be inside admitted watched directories')\n"
                               'def admitted_inputs(b):\n'
                               "    need(b.get('execution_context') == 'CLOUD_EXECUTOR_V1', 'cloud execution "
                               "context only')\n"
                               "    for name in ('cloud_budget.py', 'executor_identity.py', "
                               "'execution_mode.py'):\n"
                               '        path = D.parent / name\n'
                               "        need(b['pins'].get(str(path)) == sha(path), 'cloud admission helper "
                               "source pin')\n"
                               "    budget_module = mod('actual_cloud_budget', D.parent / "
                               "'cloud_budget.py')\n"
                               '    budget = budget_module.admit(b)\n'
                               "    budget_document = json.loads(P(b['cloud_budget']['path']).read_text())\n"
                               "    budget_module.verify_host(budget_document['host_identity'], "
                               "b['identity'])\n"
                               "    for k in ('runtime_mode', 'archive_mode', 'runtime_reuse_manifest', "
                               "'job_budget_seconds', 'budgets', 'dut_rss_bytes', 'dut_address_space_bytes', "
                               "'numeric_reserved_increment_bytes', 'reserved_other_owner_bytes', "
                               "'consumer_address_space_bytes', 'stage_resources', 'execution_mode', "
                               "'full_block_budget'):\n"
                               "        need(b.get(k) == budget[k], 'binding must exactly preserve reviewed "
                               "cloud budget ' + k)\n"
                               "    if budget['execution_mode'] == 'STAGE_COVERAGE_DIAGNOSTIC':\n"
                               "        need(b.get('stage_coverage_budget') is not None and "
                               "b['stage_coverage_budget'] == budget.get('stage_coverage_budget'), 'binding "
                               "reviewed stage coverage budget')\n"
                               '    else:\n'
                               "        need(b.get('stage_coverage_budget') is None and "
                               "budget.get('stage_coverage_budget') is None, 'stage budget forbidden in "
                               "other modes')\n"
                               "    for k in ('executor_adaptation', 'workspace_loader', "
                               "'retained_materials', 'model_candidate_review', 'p0_provider_reuse'):\n"
                               '        if k in budget or k in b:\n'
                               "            need(k in budget and b.get(k) == budget[k], 'binding reviewed ' "
                               '+ k)\n'
                               "    identity = b['identity']\n"
                               "    need(b.get('executor_identity') == identity, 'one executor identity')\n"
                               "    mod('actual_cloud_identity', D.parent / "
                               "'executor_identity.py').verify_current(identity)\n"
                               "    need(b['job_started_monotonic'] == identity['started_monotonic'], 'same "
                               "executor clock never reset')\n"
                               '\n'
                               '    def checked(row, limit):\n'
                               "        path = P(row['path'])\n"
                               '        need(path.is_absolute() and path == path.resolve() and all((not '
                               'q.is_symlink() for q in (path, *path.parents))) and path.is_file() and (0 < '
                               "path.stat().st_size <= limit), 'bounded regular cloud input')\n"
                               "        need(pin(path) == row, 'independent cloud input pin')\n"
                               '        return path\n'
                               "    identity_path = checked(b['executor_identity_pin'], 65536)\n"
                               "    need(json.loads(identity_path.read_text()) == identity, 'executor "
                               "receipt identity')\n"
                               "    manifest = checked(b['artifact_manifest'], 65536)\n"
                               '    frozen = json.loads(manifest.read_text())\n'
                               "    handoff = checked(b['builder_handoff'], 65536)\n"
                               "    candidate = frozen.get('schema') == "
                               "'MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1'\n"
                               "    extra = {'executor_adaptation': b['executor_adaptation']} if "
                               "'executor_adaptation' in b else {}\n"
                               "    hpath = D.parent / 'numeric/artifact_handoff.py'\n"
                               '    reviewed = None\n'
                               '    if candidate:\n'
                               "        need(b.get('model_candidate_review') is not None, "
                               "'MODEL_CANDIDATE_REVIEW_REQUIRED')\n"
                               "        path = D.parent / 'numeric/candidate_admission.py'\n"
                               "        need(b['pins'].get(str(path)) == sha(path), 'model candidate "
                               "admission source pin')\n"
                               "        reviewed = mod('flow_model_candidate_admission', "
                               "path).verify(b['model_candidate_review'], b)\n"
                               "        need(reviewed['scope'] == "
                               "'MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL' and "
                               "reviewed['artifact_manifest_sha256'] == b['artifact_manifest']['sha256'], "
                               "'actual candidate review scope/artifact')\n"
                               "        hpath = D.parent / 'numeric/candidate_artifact_handoff.py'\n"
                               "        extra.update(model_candidate_review=b['model_candidate_review'], "
                               "current_source_pins_pin=b['source_pins'], repo=P(b['repo']))\n"
                               '    else:\n'
                               "        need('model_candidate_review' not in b, 'model review cannot relabel "
                               "legacy artifact')\n"
                               "    need(b['pins'].get(str(hpath)) == sha(hpath), 'handoff verifier source "
                               "pin')\n"
                               "    imported = mod('actual_imported_artifact', hpath).verify(handoff, "
                               "b['builder_handoff']['sha256'], manifest, b['artifact_manifest']['sha256'], "
                               'frozen, identity, **extra)\n'
                               '    if reviewed is not None:\n'
                               '        imported = dict(imported, model_candidate_verified=reviewed)\n'
                               "    need(imported['builder_identity'] == b['artifact_identity'], 'separate "
                               "actual builder identity')\n"
                               "    sourcepins = D.parent / 'SOURCE_PINS.json'\n"
                               "    need(pin(sourcepins) == b['source_pins'], 'actual executor source "
                               "closure pin')\n"
                               "    if 'executor_adaptation' in b:\n"
                               "        apath = D.parent / 'executor_adaptation.py'\n"
                               "        need(b['pins'].get(str(apath)) == sha(apath), 'adaptation verifier "
                               "source pin')\n"
                               "        mod('actual_executor_adaptation', "
                               "apath).verify(b['executor_adaptation'], imported['builder_identity'], "
                               "identity, current_source_pins_pin=b['source_pins'], repo=P(b['repo']))\n"
                               "        loader_path = D.parent / 'numeric/workspace_loader.py'\n"
                               "        abi_path = D.parent / 'numeric/runtime_abi_owned.py'\n"
                               '        for path in (loader_path, abi_path):\n'
                               "            need(b['pins'].get(str(path)) == sha(path), 'workspace ABI "
                               "helper source pin')\n"
                               '        artifact_root = manifest.parent\n'
                               "        binary = frozen['common']['binary']\n"
                               "        tool = frozen['tool_manifest']\n"
                               "        verified = mod('actual_cloud_workspace_loader', "
                               "loader_path).verify(b['workspace_loader'], artifact_root / binary['path'], "
                               "binary['sha256'], artifact_root / tool['path'], tool['sha256'], "
                               "mod('actual_cloud_runtime_abi', abi_path).elf_info)\n"
                               "        need(verified['artifact_manifest_sha256'] == "
                               "b['artifact_manifest']['sha256'] and verified['builder_source_commit'] == "
                               "b['artifact_identity']['source_commit'], 'workspace loader actual "
                               "builder/artifact binding')\n"
                               '        imported = dict(imported, workspace_loader_verified=verified)\n'
                               '    else:\n'
                               "        need(imported['source_pins_sha256'] == sha(sourcepins), 'imported "
                               "build reviewed source closure')\n"
                               "    need(subprocess.check_output(['git', '-C', b['repo'], 'rev-parse', "
                               "'HEAD'], text=True).strip() == identity['source_commit'], 'actual executor "
                               "source commit')\n"
                               "    if 'retained_materials' in b:\n"
                               "        retained_path = D.parent / 'runtime/retained_materials.py'\n"
                               "        need(b['pins'].get(str(retained_path)) == sha(retained_path), "
                               "'retained materials verifier source pin')\n"
                               "        retained = mod('actual_retained_materials', "
                               "retained_path).verify(b['retained_materials'], b)\n"
                               '        if candidate:\n'
                               "            need(retained['scope'] == "
                               "'DATA_REFERENCE_ONLY_NOT_NUMERICAL_ABI_OR_RUNTIME_PASS', 'candidate retained "
                               "data/reference only')\n"
                               '        imported = dict(imported, retained_materials_verified=retained)\n'
                               '    reused = verified_p0_provider_reuse(b, budget, candidate)\n'
                               '    if reused is not None:\n'
                               '        imported = dict(imported, p0_provider_reuse_verified=reused)\n'
                               '    return (budget, imported)',
                               'def admitted_inputs(b):\n'
                               "    need(b.get('execution_context') == 'CLOUD_EXECUTOR_V1', 'cloud execution "
                               "context only')\n"
                               "    for name in ('cloud_budget.py', 'executor_identity.py', "
                               "'execution_mode.py'):\n"
                               '        path = D.parent / name\n'
                               "        need(b['pins'].get(str(path)) == sha(path), 'cloud admission helper "
                               "source pin')\n"
                               "    budget_module = mod('actual_cloud_budget', D.parent / "
                               "'cloud_budget.py')\n"
                               '    budget = budget_module.admit(b)\n'
                               "    budget_document = json.loads(P(b['cloud_budget']['path']).read_text())\n"
                               "    budget_module.verify_host(budget_document['host_identity'], "
                               "b['identity'])\n"
                               "    for k in ('runtime_mode', 'archive_mode', 'runtime_reuse_manifest', "
                               "'job_budget_seconds', 'budgets', 'dut_rss_bytes', 'dut_address_space_bytes', "
                               "'numeric_reserved_increment_bytes', 'reserved_other_owner_bytes', "
                               "'consumer_address_space_bytes', 'stage_resources', 'execution_mode', "
                               "'full_block_budget'):\n"
                               "        need(b.get(k) == budget[k], 'binding must exactly preserve reviewed "
                               "cloud budget ' + k)\n"
                               "    for k in ('executor_adaptation', 'workspace_loader', "
                               "'retained_materials', 'model_candidate_review'):\n"
                               '        if k in budget or k in b:\n'
                               "            need(k in budget and b.get(k) == budget[k], 'binding reviewed ' "
                               '+ k)\n'
                               "    identity = b['identity']\n"
                               "    need(b.get('executor_identity') == identity, 'one executor identity')\n"
                               "    mod('actual_cloud_identity', D.parent / "
                               "'executor_identity.py').verify_current(identity)\n"
                               "    need(b['job_started_monotonic'] == identity['started_monotonic'], 'same "
                               "executor clock never reset')\n"
                               '\n'
                               '    def checked(row, limit):\n'
                               "        path = P(row['path'])\n"
                               '        need(path.is_absolute() and path == path.resolve() and all((not '
                               'q.is_symlink() for q in (path, *path.parents))) and path.is_file() and (0 < '
                               "path.stat().st_size <= limit), 'bounded regular cloud input')\n"
                               "        need(pin(path) == row, 'independent cloud input pin')\n"
                               '        return path\n'
                               "    identity_path = checked(b['executor_identity_pin'], 65536)\n"
                               "    need(json.loads(identity_path.read_text()) == identity, 'executor "
                               "receipt identity')\n"
                               "    manifest = checked(b['artifact_manifest'], 65536)\n"
                               '    frozen = json.loads(manifest.read_text())\n'
                               "    handoff = checked(b['builder_handoff'], 65536)\n"
                               "    candidate = frozen.get('schema') == "
                               "'MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1'\n"
                               "    extra = {'executor_adaptation': b['executor_adaptation']} if "
                               "'executor_adaptation' in b else {}\n"
                               "    hpath = D.parent / 'numeric/artifact_handoff.py'\n"
                               '    reviewed = None\n'
                               '    if candidate:\n'
                               "        need(b.get('model_candidate_review') is not None, "
                               "'MODEL_CANDIDATE_REVIEW_REQUIRED')\n"
                               "        path = D.parent / 'numeric/candidate_admission.py'\n"
                               "        need(b['pins'].get(str(path)) == sha(path), 'model candidate "
                               "admission source pin')\n"
                               "        reviewed = mod('flow_model_candidate_admission', "
                               "path).verify(b['model_candidate_review'], b)\n"
                               "        need(reviewed['scope'] == "
                               "'MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL' and "
                               "reviewed['artifact_manifest_sha256'] == b['artifact_manifest']['sha256'], "
                               "'actual candidate review scope/artifact')\n"
                               "        hpath = D.parent / 'numeric/candidate_artifact_handoff.py'\n"
                               "        extra.update(model_candidate_review=b['model_candidate_review'], "
                               "current_source_pins_pin=b['source_pins'], repo=P(b['repo']))\n"
                               '    else:\n'
                               "        need('model_candidate_review' not in b, 'model review cannot relabel "
                               "legacy artifact')\n"
                               "    need(b['pins'].get(str(hpath)) == sha(hpath), 'handoff verifier source "
                               "pin')\n"
                               "    imported = mod('actual_imported_artifact', hpath).verify(handoff, "
                               "b['builder_handoff']['sha256'], manifest, b['artifact_manifest']['sha256'], "
                               'frozen, identity, **extra)\n'
                               '    if reviewed is not None:\n'
                               '        imported = dict(imported, model_candidate_verified=reviewed)\n'
                               "    need(imported['builder_identity'] == b['artifact_identity'], 'separate "
                               "actual builder identity')\n"
                               "    sourcepins = D.parent / 'SOURCE_PINS.json'\n"
                               "    need(pin(sourcepins) == b['source_pins'], 'actual executor source "
                               "closure pin')\n"
                               "    if 'executor_adaptation' in b:\n"
                               "        apath = D.parent / 'executor_adaptation.py'\n"
                               "        need(b['pins'].get(str(apath)) == sha(apath), 'adaptation verifier "
                               "source pin')\n"
                               "        mod('actual_executor_adaptation', "
                               "apath).verify(b['executor_adaptation'], imported['builder_identity'], "
                               "identity, current_source_pins_pin=b['source_pins'], repo=P(b['repo']))\n"
                               "        loader_path = D.parent / 'numeric/workspace_loader.py'\n"
                               "        abi_path = D.parent / 'numeric/runtime_abi_owned.py'\n"
                               '        for path in (loader_path, abi_path):\n'
                               "            need(b['pins'].get(str(path)) == sha(path), 'workspace ABI "
                               "helper source pin')\n"
                               '        artifact_root = manifest.parent\n'
                               "        binary = frozen['common']['binary']\n"
                               "        tool = frozen['tool_manifest']\n"
                               "        verified = mod('actual_cloud_workspace_loader', "
                               "loader_path).verify(b['workspace_loader'], artifact_root / binary['path'], "
                               "binary['sha256'], artifact_root / tool['path'], tool['sha256'], "
                               "mod('actual_cloud_runtime_abi', abi_path).elf_info)\n"
                               "        need(verified['artifact_manifest_sha256'] == "
                               "b['artifact_manifest']['sha256'] and verified['builder_source_commit'] == "
                               "b['artifact_identity']['source_commit'], 'workspace loader actual "
                               "builder/artifact binding')\n"
                               '        imported = dict(imported, workspace_loader_verified=verified)\n'
                               '    else:\n'
                               "        need(imported['source_pins_sha256'] == sha(sourcepins), 'imported "
                               "build reviewed source closure')\n"
                               "    need(subprocess.check_output(['git', '-C', b['repo'], 'rev-parse', "
                               "'HEAD'], text=True).strip() == identity['source_commit'], 'actual executor "
                               "source commit')\n"
                               "    if 'retained_materials' in b:\n"
                               "        retained_path = D.parent / 'runtime/retained_materials.py'\n"
                               "        need(b['pins'].get(str(retained_path)) == sha(retained_path), "
                               "'retained materials verifier source pin')\n"
                               "        retained = mod('actual_retained_materials', "
                               "retained_path).verify(b['retained_materials'], b)\n"
                               '        if candidate:\n'
                               "            need(retained['scope'] == "
                               "'DATA_REFERENCE_ONLY_NOT_NUMERICAL_ABI_OR_RUNTIME_PASS', 'candidate retained "
                               "data/reference only')\n"
                               '        imported = dict(imported, retained_materials_verified=retained)\n'
                               '    return (budget, imported)'),
                              ('1009a961dc429317db183e83665aed262217b25b2eb70ba7f20ac0bb02b45ebe',
                               'roots = list(dict.fromkeys([str(job), str(repo), '
                               "*[str(P(b[k]['path']).parent) for k in ('artifact_manifest', "
                               "'builder_handoff', 'executor_identity_pin', 'cloud_budget', "
                               "'execution_approval', 'executor_adaptation', 'workspace_loader', "
                               "'retained_materials', 'model_candidate_review', 'stage_coverage_budget') if "
                               'k in b]]))',
                               'roots = list(dict.fromkeys([str(job), str(repo), '
                               "*[str(P(b[k]['path']).parent) for k in ('artifact_manifest', "
                               "'builder_handoff', 'executor_identity_pin', 'cloud_budget', "
                               "'execution_approval', 'executor_adaptation', 'workspace_loader', "
                               "'retained_materials', 'model_candidate_review') if k in b]]))"),
                              ('a61f49752ddbac36c2f6a02299341d529d1835dc3478e4228adce6da5d5c29ee',
                               "if 'p0_provider_reuse' in b:\n"
                               "    need('p0_provider_reuse_verified' in imported, 'P0 pure data roots "
                               "verified before watch admission')\n"
                               "    roots.extend(imported['p0_provider_reuse_verified']['roots'])\n"
                               '    roots = list(dict.fromkeys(roots))',
                               ''),
                              ('c93b917ac25452255c0bff2a6fe2e87a30da7a9aca50a5ada89169ce0790693b',
                               'stage_budget_watch_coverage(b, roots)',
                               ''),
                              ('9ae682655625975506e92a815f6c81f28148fef939c4df5d7ffaf22f8c78f755',
                               "body.update({k: b[k] for k in ('executor_adaptation', 'workspace_loader', "
                               "'retained_materials', 'model_candidate_review', 'p0_provider_reuse') if k in "
                               'b})',
                               "body.update({k: b[k] for k in ('executor_adaptation', 'workspace_loader', "
                               "'retained_materials', 'model_candidate_review') if k in b})"),
                              ('2affc2dd2b09bf620df526ef00c755ce5ff14ceaf7eb647d21a8343ff457c593',
                               "if admission['mode'] == 'STAGE_COVERAGE_DIAGNOSTIC':\n"
                               "    body['stage_coverage_budget'] = b['stage_coverage_budget']",
                               ''),
                              ('21646ac7f44373da3743a4aed6201ed3ca9f2413d9e861ab5c692f1ce0731d81',
                               "save(job / 'FLOW_RESULT.json', dict(execution_context='CLOUD_EXECUTOR_V1', "
                               'identity=identity, executor_identity=identity, artifact_identity=builder, '
                               "builder_identity=builder, source_pins=b['source_pins'], "
                               "executor_identity_pin=b['executor_identity_pin'], "
                               "builder_handoff=b['builder_handoff'], "
                               "artifact_manifest=b['artifact_manifest'], cloud_budget=b['cloud_budget'], "
                               "execution_approval=b['execution_approval'], job_budget_seconds=limit, "
                               'execution_binding=pin(binding_path), execution_admission=admission, '
                               "execution_mode=admission['mode'], transport_exit_code=code, "
                               'qualification=qualification, execution_policy=execution_policy, '
                               "status=qualification['status'], "
                               "scope='MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL' if "
                               "'model_candidate_review' in b else "
                               "'CHISEL_TEST_GENERATED_SIMULATION_BACKEND_NOT_FINAL_RTL', stages=history, "
                               "retained_materials_scope=imported.get('retained_materials_verified', "
                               "{}).get('scope'), upfront_disk_admission=disk_admission, "
                               'numeric_result=pin(numeric_path), hardware_definitions=1, '
                               'profiles=list(range(5)), uploaded_payloads=False, **{k: b[k] for k in '
                               "('executor_adaptation', 'workspace_loader', 'retained_materials', "
                               "'model_candidate_review', 'p0_provider_reuse') if k in b}, "
                               "**dict(stage_coverage_budget=b['stage_coverage_budget'], "
                               "stage_coverage_budget_sha256=b['stage_coverage_budget']['sha256'], "
                               "execution_scope='STAGE_COVERAGE_DIAGNOSTIC_NOT_FULL_ACCEPTANCE') if "
                               "admission['mode'] == 'STAGE_COVERAGE_DIAGNOSTIC' else {}))",
                               "save(job / 'FLOW_RESULT.json', dict(execution_context='CLOUD_EXECUTOR_V1', "
                               'identity=identity, executor_identity=identity, artifact_identity=builder, '
                               "builder_identity=builder, source_pins=b['source_pins'], "
                               "executor_identity_pin=b['executor_identity_pin'], "
                               "builder_handoff=b['builder_handoff'], "
                               "artifact_manifest=b['artifact_manifest'], cloud_budget=b['cloud_budget'], "
                               "execution_approval=b['execution_approval'], job_budget_seconds=limit, "
                               'execution_binding=pin(binding_path), execution_admission=admission, '
                               "execution_mode=admission['mode'], transport_exit_code=code, "
                               'qualification=qualification, execution_policy=execution_policy, '
                               "status=qualification['status'], "
                               "scope='MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL' if "
                               "'model_candidate_review' in b else "
                               "'CHISEL_TEST_GENERATED_SIMULATION_BACKEND_NOT_FINAL_RTL', stages=history, "
                               "retained_materials_scope=imported.get('retained_materials_verified', "
                               "{}).get('scope'), upfront_disk_admission=disk_admission, "
                               'numeric_result=pin(numeric_path), hardware_definitions=1, '
                               'profiles=list(range(5)), uploaded_payloads=False, **{k: b[k] for k in '
                               "('executor_adaptation', 'workspace_loader', 'retained_materials', "
                               "'model_candidate_review') if k in b}))")]}

# Exact inverse of the reviewed stage-coverage / P0 data-only additions.
# Mandatory unique full-AST snippet matches; original historical whole-AST hashes
# below remain unchanged. No arbitrary mode branch or dependency gate is skipped.
# Reference data-only delta: restore exact 82bafa AST before the prior reviewed inverse.
REVIEWED_REFERENCE_INVERSE = {'controller/cloud_flow.py': [('4341d10fc595b5c3eb83ad7db93b24f8cdf4ee85abd45c17519a5d85586bbf0f',
                               'def verified_reference_data_reuse(b, budget, candidate):\n'
                               "    if 'reference_data_reuse' not in b:\n"
                               '        return None\n'
                               "    need(candidate and budget['execution_mode'] == "
                               "'STAGE_COVERAGE_DIAGNOSTIC', 'reference reuse only approved candidate "
                               "stage')\n"
                               "    need(b['reference_data_reuse'] == budget.get('reference_data_reuse'), "
                               "'reference reuse independently approved pin')\n"
                               "    path = D.parent / 'numeric/reference_data_reuse.py'\n"
                               "    need(b['pins'].get(str(path)) == sha(path), 'reference data reuse "
                               "checker source pin')\n"
                               "    reused = mod('actual_reference_data_reuse', "
                               "path).verify_metadata(b['reference_data_reuse'], b)\n"
                               "    need(reused['scope'] == "
                               "'READONLY_REFERENCE_TENSOR_HARDLINKS_NOT_DUT_PASS' and reused['tree_cap'] == "
                               "budget.get('aggregate_tree_cap_bytes') == 12037043872, 'reference reuse "
                               "exact approved scope/tree')\n"
                               "    need(len(reused['roots']) == 5 and len(set(reused['roots'])) == 5, 'five "
                               "distinct verified reference roots')\n"
                               '    return reused',
                               ''),
                              ('483a7d2269081dd05e5e56ae35f8c1a4006067f4cbc3530c957b05f26c99da29',
                               "for k in ('executor_adaptation', 'workspace_loader', 'retained_materials', "
                               "'model_candidate_review', 'p0_provider_reuse', 'reference_data_reuse', "
                               "'aggregate_tree_cap_bytes'):\n"
                               '    if k in budget or k in b:\n'
                               "        need(k in budget and b.get(k) == budget[k], 'binding reviewed ' + k)",
                               "for k in ('executor_adaptation', 'workspace_loader', 'retained_materials', "
                               "'model_candidate_review', 'p0_provider_reuse'):\n"
                               '    if k in budget or k in b:\n'
                               "        need(k in budget and b.get(k) == budget[k], 'binding reviewed ' + "
                               'k)'),
                              ('c1987cbcc24181f1c18e3529aa48ec25177093404236f35b737a01c62a1ef5f5',
                               'reused_refs = verified_reference_data_reuse(b, budget, candidate)\n'
                               'if reused_refs is not None:\n'
                               '    imported = dict(imported, reference_data_reuse_verified=reused_refs)\n'
                               "if 'reference_data_reuse' in b:\n"
                               "    need(budget['runtime_mode'] == 'IMPORT_EXISTING_PINNED_RUNTIME' and "
                               "budget['archive_mode'] == 'READ_EXISTING_PINNED_ARCHIVES', 'reference reuse "
                               "requires explicitly revalidated retained runtime')\n"
                               'reused = verified_p0_provider_reuse(b, budget, candidate)',
                               'reused = verified_p0_provider_reuse(b, budget, candidate)'),
                              ('8c52b20c9107cf1de20a689eb20e2f8dd5ad1148c24aadee846b7d914bf6d06a',
                               'def runtime_admission_fields(b):\n'
                               "    return {k: b[k] for k in ('execution_mode', 'full_block_budget', "
                               "'stage_coverage_budget', 'p0_provider_reuse', 'reference_data_reuse', "
                               "'aggregate_tree_cap_bytes', 'executor_adaptation', 'workspace_loader', "
                               "'retained_materials', 'model_candidate_review') if k in b}",
                               ''),
                              ('954b92e949a5a5de0717163fad52e1f92e5c85402d5e1bc4e7c9859a8748fd1a',
                               'def upfront_disk_admission(snapshot, evidence_path=None, binding_sha=None, '
                               'tree_cap=TREE):\n'
                               '    need(type(tree_cap) is int and tree_cap in (TREE, 12037043872), '
                               "'explicit reviewed unchanged or tighter aggregate cap')\n"
                               "    need(snapshot.get('schema') == 'SAMPLED_OWNED_LIVE_BYTES_V1' and "
                               "snapshot.get('complete') is True, 'complete upfront watched-root census')\n"
                               "    live = snapshot['bytes']\n"
                               "    free = snapshot['free_bytes']\n"
                               '    need(type(live) is int and 0 <= live <= tree_cap and (type(free) is int) '
                               "and (free >= 0), 'bounded existing watched bytes/free')\n"
                               '    incremental = tree_cap - live\n'
                               '    required = incremental + (8 << 30)\n'
                               '    if evidence_path is not None:\n'
                               '        bounded = lambda v: v if type(v) is int and 0 <= v < 2 ** 64 else '
                               'None\n'
                               '        digest = binding_sha if isinstance(binding_sha, str) and '
                               "len(binding_sha) == 64 and all((c in '0123456789abcdef' for c in "
                               'binding_sha)) else None\n'
                               "        save(evidence_path, dict(schema='CLOUD_UPFRONT_DISK_OBSERVATION_V1', "
                               "scope='SAMPLED_PLANNING_ONLY_PHASE_GATES_UNCHANGED', binding_sha256=digest, "
                               "census_schema='SAMPLED_OWNED_LIVE_BYTES_V1', census_complete=True, "
                               'existing_watched_bytes=bounded(live), '
                               'maximum_additional_bytes=bounded(incremental), free_reserve_bytes=8 << 30, '
                               'required_free_bytes=bounded(required), observed_free_bytes=bounded(free), '
                               'shortfall_bytes=bounded(max(0, required - free)), '
                               "status='SUFFICIENT_SAMPLED_SPACE' if free >= required else "
                               "'REJECTED_INSUFFICIENT_SAMPLED_SPACE', numerical_pass=False, "
                               'job_created=False))\n'
                               "    need(free >= required, 'remaining aggregate growth plus unchanged "
                               "free8GiB')\n"
                               '    return dict(existing_watched_bytes=live, '
                               'maximum_additional_bytes=incremental, free_reserve_bytes=8 << 30, '
                               'required_free_bytes=required, observed_free_bytes=free, '
                               "scope='SAMPLED_PLANNING_ONLY_PHASE_GATES_UNCHANGED')",
                               'def upfront_disk_admission(snapshot, evidence_path=None, binding_sha=None):\n'
                               "    need(snapshot.get('schema') == 'SAMPLED_OWNED_LIVE_BYTES_V1' and "
                               "snapshot.get('complete') is True, 'complete upfront watched-root census')\n"
                               "    live = snapshot['bytes']\n"
                               "    free = snapshot['free_bytes']\n"
                               '    need(type(live) is int and 0 <= live <= TREE and (type(free) is int) and '
                               "(free >= 0), 'bounded existing watched bytes/free')\n"
                               '    incremental = TREE - live\n'
                               '    required = incremental + (8 << 30)\n'
                               '    if evidence_path is not None:\n'
                               '        bounded = lambda v: v if type(v) is int and 0 <= v < 2 ** 64 else '
                               'None\n'
                               '        digest = binding_sha if isinstance(binding_sha, str) and '
                               "len(binding_sha) == 64 and all((c in '0123456789abcdef' for c in "
                               'binding_sha)) else None\n'
                               "        save(evidence_path, dict(schema='CLOUD_UPFRONT_DISK_OBSERVATION_V1', "
                               "scope='SAMPLED_PLANNING_ONLY_PHASE_GATES_UNCHANGED', binding_sha256=digest, "
                               "census_schema='SAMPLED_OWNED_LIVE_BYTES_V1', census_complete=True, "
                               'existing_watched_bytes=bounded(live), '
                               'maximum_additional_bytes=bounded(incremental), free_reserve_bytes=8 << 30, '
                               'required_free_bytes=bounded(required), observed_free_bytes=bounded(free), '
                               'shortfall_bytes=bounded(max(0, required - free)), '
                               "status='SUFFICIENT_SAMPLED_SPACE' if free >= required else "
                               "'REJECTED_INSUFFICIENT_SAMPLED_SPACE', numerical_pass=False, "
                               'job_created=False))\n'
                               "    need(free >= required, 'remaining aggregate growth plus unchanged "
                               "free8GiB')\n"
                               '    return dict(existing_watched_bytes=live, '
                               'maximum_additional_bytes=incremental, free_reserve_bytes=8 << 30, '
                               'required_free_bytes=required, observed_free_bytes=free, '
                               "scope='SAMPLED_PLANNING_ONLY_PHASE_GATES_UNCHANGED')"),
                              ('a5058fa13f35888e60a6c14624f6680bbc61e3648306b334fafa31cdea7d7f4b',
                               "tree_cap = budget.get('aggregate_tree_cap_bytes', TREE)\n"
                               "need(b.get('aggregate_tree_cap_bytes', TREE) == tree_cap, 'same approved "
                               "aggregate cap')\n"
                               "profile_policy.require_source_pin(b['pins'])",
                               "profile_policy.require_source_pin(b['pins'])"),
                              ('34d49cff427445e7cf2f222de8aaf7db046c8c068a32c2d7fdbe79712bf99c07',
                               "if 'reference_data_reuse' in b:\n"
                               "    need('reference_data_reuse_verified' in imported, 'reference roots "
                               "verified before watch admission')\n"
                               "    roots.extend(imported['reference_data_reuse_verified']['roots'])\n"
                               '    roots = list(dict.fromkeys(roots))\n'
                               "if 'p0_provider_reuse' in b:\n"
                               "    need('p0_provider_reuse_verified' in imported, 'P0 pure data roots "
                               "verified before watch admission')\n"
                               "    roots.extend(imported['p0_provider_reuse_verified']['roots'])\n"
                               '    roots = list(dict.fromkeys(roots))',
                               "if 'p0_provider_reuse' in b:\n"
                               "    need('p0_provider_reuse_verified' in imported, 'P0 pure data roots "
                               "verified before watch admission')\n"
                               "    roots.extend(imported['p0_provider_reuse_verified']['roots'])\n"
                               '    roots = list(dict.fromkeys(roots))'),
                              ('830f31807c87421b8f5177d9ca8e4af1391e2d3feac56ffb1b4d1a135cf002e2',
                               'disk_admission = upfront_disk_admission(snapshot, '
                               "P(binding_path).with_name(P(binding_path).name + '.UPFRONT_DISK.json'), "
                               'binding_sha, tree_cap=tree_cap)',
                               'disk_admission = upfront_disk_admission(snapshot, '
                               "P(binding_path).with_name(P(binding_path).name + '.UPFRONT_DISK.json'), "
                               'binding_sha)'),
                              ('f11012d37ffd96f6e3d1295423c53035995a58134e0daa82f35043ed12eb13cf',
                               'caps = dict(wall_seconds=seconds, cleanup_seconds=30, file_bytes=2 << 30, '
                               "tree_bytes=policy['output_bytes'], watch_tree_bytes=tree_cap, "
                               'extra_watch_roots=roots, min_free_disk_bytes=1500000000, log_bytes=64 << 20, '
                               'raw_log_bytes=128 << 20, max_entries=150000, '
                               "per_process_as_bytes=policy['as_bytes'], "
                               "per_process_cpu_seconds=policy['cpu_seconds'], "
                               "rss_bytes=policy['rss_bytes'], cpu_seconds=policy['cpu_seconds'])",
                               'caps = dict(wall_seconds=seconds, cleanup_seconds=30, file_bytes=2 << 30, '
                               "tree_bytes=policy['output_bytes'], watch_tree_bytes=TREE, "
                               'extra_watch_roots=roots, min_free_disk_bytes=1500000000, log_bytes=64 << 20, '
                               'raw_log_bytes=128 << 20, max_entries=150000, '
                               "per_process_as_bytes=policy['as_bytes'], "
                               "per_process_cpu_seconds=policy['cpu_seconds'], "
                               "rss_bytes=policy['rss_bytes'], cpu_seconds=policy['cpu_seconds'])"),
                              ('37ab5972a6283522da61c40eb8c72bd4a087f236e4315c44f7edac847914d731',
                               'install_binding.update(runtime_admission_fields(b))',
                               "install_binding.update({k: b[k] for k in ('executor_adaptation', "
                               "'workspace_loader', 'retained_materials', 'model_candidate_review') if k in "
                               'b})'),
                              ('c9bd6216c0260e9cf356b51b769f43b4363027c0f4583db709fe613e286b4303',
                               'body = dict(execution_policy=execution_policy, '
                               "schema='SAME_JOB_FIVE_M128_DIAGNOSTIC_TAIL_V1', profiles=list(range(5)), "
                               'tokens=128, matrix_macs=4096, vector_lanes=32, upload_payloads=False, '
                               'final_rtl_replay=False, references=references, weights=weights, '
                               "calibration_seconds=q['calibration_seconds'], job_started_monotonic=started, "
                               "reserved_material_seconds=7 * q['provider'] + 11 * 120, "
                               "reserved_cleanup_seconds=1530, reserved_parent_seconds=q['parent'], "
                               "tree_cap=tree_cap, rss_bytes=b['dut_rss_bytes'], "
                               "address_space_bytes=b['dut_address_space_bytes'], "
                               "reserved_other_owner_bytes=b['reserved_other_owner_bytes'], "
                               "consumer_address_space_bytes=b['consumer_address_space_bytes'], "
                               "phase_extra_bytes=b['numeric_reserved_increment_bytes'], "
                               "provider_wall_seconds=q['provider'], pins=pins, output=str(owner_root / "
                               "'numeric'), owned_roots=roots, owner_root=str(owner_root), "
                               'owner_module=str(owner_module), owner_manifest=owner_pin, '
                               "supervisor_dir=supervisor_dir, execution_context='CLOUD_EXECUTOR_V1', "
                               'identity=identity, executor_identity=identity, '
                               "executor_identity_pin=b['executor_identity_pin'], "
                               "builder_handoff=b['builder_handoff'], "
                               "artifact_manifest=b['artifact_manifest'], cloud_budget=b['cloud_budget'], "
                               "execution_approval=b['execution_approval'], "
                               'controller_binding=pin(binding_path), job_budget_seconds=limit, '
                               "run_id=builder['run_id'], source_commit=builder['source_commit'], "
                               "launch_commit=builder['launch_commit'], python=py, lock=lock, "
                               "repo=str(repo), payload=str(payload), materializer=b['materializer'], "
                               'environment={})\n'
                               "body.update({k: b[k] for k in ('executor_adaptation', 'workspace_loader', "
                               "'retained_materials', 'model_candidate_review', 'p0_provider_reuse', "
                               "'reference_data_reuse', 'aggregate_tree_cap_bytes') if k in b})",
                               'body = dict(execution_policy=execution_policy, '
                               "schema='SAME_JOB_FIVE_M128_DIAGNOSTIC_TAIL_V1', profiles=list(range(5)), "
                               'tokens=128, matrix_macs=4096, vector_lanes=32, upload_payloads=False, '
                               'final_rtl_replay=False, references=references, weights=weights, '
                               "calibration_seconds=q['calibration_seconds'], job_started_monotonic=started, "
                               "reserved_material_seconds=7 * q['provider'] + 11 * 120, "
                               "reserved_cleanup_seconds=1530, reserved_parent_seconds=q['parent'], "
                               "tree_cap=TREE, rss_bytes=b['dut_rss_bytes'], "
                               "address_space_bytes=b['dut_address_space_bytes'], "
                               "reserved_other_owner_bytes=b['reserved_other_owner_bytes'], "
                               "consumer_address_space_bytes=b['consumer_address_space_bytes'], "
                               "phase_extra_bytes=b['numeric_reserved_increment_bytes'], "
                               "provider_wall_seconds=q['provider'], pins=pins, output=str(owner_root / "
                               "'numeric'), owned_roots=roots, owner_root=str(owner_root), "
                               'owner_module=str(owner_module), owner_manifest=owner_pin, '
                               "supervisor_dir=supervisor_dir, execution_context='CLOUD_EXECUTOR_V1', "
                               'identity=identity, executor_identity=identity, '
                               "executor_identity_pin=b['executor_identity_pin'], "
                               "builder_handoff=b['builder_handoff'], "
                               "artifact_manifest=b['artifact_manifest'], cloud_budget=b['cloud_budget'], "
                               "execution_approval=b['execution_approval'], "
                               'controller_binding=pin(binding_path), job_budget_seconds=limit, '
                               "run_id=builder['run_id'], source_commit=builder['source_commit'], "
                               "launch_commit=builder['launch_commit'], python=py, lock=lock, "
                               "repo=str(repo), payload=str(payload), materializer=b['materializer'], "
                               'environment={})\n'
                               "body.update({k: b[k] for k in ('executor_adaptation', 'workspace_loader', "
                               "'retained_materials', 'model_candidate_review', 'p0_provider_reuse') if k in "
                               'b})'),
                              ('1c84646710d9118f6c72cc7f6bb0d412c5fec984e7739d7aad28c6d75921d2a7',
                               "save(job / 'FLOW_RESULT.json', dict(execution_context='CLOUD_EXECUTOR_V1', "
                               'identity=identity, executor_identity=identity, artifact_identity=builder, '
                               "builder_identity=builder, source_pins=b['source_pins'], "
                               "executor_identity_pin=b['executor_identity_pin'], "
                               "builder_handoff=b['builder_handoff'], "
                               "artifact_manifest=b['artifact_manifest'], cloud_budget=b['cloud_budget'], "
                               "execution_approval=b['execution_approval'], job_budget_seconds=limit, "
                               'execution_binding=pin(binding_path), execution_admission=admission, '
                               "execution_mode=admission['mode'], transport_exit_code=code, "
                               'qualification=qualification, execution_policy=execution_policy, '
                               "status=qualification['status'], "
                               "scope='MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL' if "
                               "'model_candidate_review' in b else "
                               "'CHISEL_TEST_GENERATED_SIMULATION_BACKEND_NOT_FINAL_RTL', stages=history, "
                               "retained_materials_scope=imported.get('retained_materials_verified', "
                               "{}).get('scope'), upfront_disk_admission=disk_admission, "
                               'numeric_result=pin(numeric_path), hardware_definitions=1, '
                               'profiles=list(range(5)), uploaded_payloads=False, **{k: b[k] for k in '
                               "('executor_adaptation', 'workspace_loader', 'retained_materials', "
                               "'model_candidate_review', 'p0_provider_reuse', 'reference_data_reuse', "
                               "'aggregate_tree_cap_bytes') if k in b}, "
                               "**dict(stage_coverage_budget=b['stage_coverage_budget'], "
                               "stage_coverage_budget_sha256=b['stage_coverage_budget']['sha256'], "
                               "execution_scope='STAGE_COVERAGE_DIAGNOSTIC_NOT_FULL_ACCEPTANCE') if "
                               "admission['mode'] == 'STAGE_COVERAGE_DIAGNOSTIC' else {}))",
                               "save(job / 'FLOW_RESULT.json', dict(execution_context='CLOUD_EXECUTOR_V1', "
                               'identity=identity, executor_identity=identity, artifact_identity=builder, '
                               "builder_identity=builder, source_pins=b['source_pins'], "
                               "executor_identity_pin=b['executor_identity_pin'], "
                               "builder_handoff=b['builder_handoff'], "
                               "artifact_manifest=b['artifact_manifest'], cloud_budget=b['cloud_budget'], "
                               "execution_approval=b['execution_approval'], job_budget_seconds=limit, "
                               'execution_binding=pin(binding_path), execution_admission=admission, '
                               "execution_mode=admission['mode'], transport_exit_code=code, "
                               'qualification=qualification, execution_policy=execution_policy, '
                               "status=qualification['status'], "
                               "scope='MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL' if "
                               "'model_candidate_review' in b else "
                               "'CHISEL_TEST_GENERATED_SIMULATION_BACKEND_NOT_FINAL_RTL', stages=history, "
                               "retained_materials_scope=imported.get('retained_materials_verified', "
                               "{}).get('scope'), upfront_disk_admission=disk_admission, "
                               'numeric_result=pin(numeric_path), hardware_definitions=1, '
                               'profiles=list(range(5)), uploaded_payloads=False, **{k: b[k] for k in '
                               "('executor_adaptation', 'workspace_loader', 'retained_materials', "
                               "'model_candidate_review', 'p0_provider_reuse') if k in b}, "
                               "**dict(stage_coverage_budget=b['stage_coverage_budget'], "
                               "stage_coverage_budget_sha256=b['stage_coverage_budget']['sha256'], "
                               "execution_scope='STAGE_COVERAGE_DIAGNOSTIC_NOT_FULL_ACCEPTANCE') if "
                               "admission['mode'] == 'STAGE_COVERAGE_DIAGNOSTIC' else {}))")]}
# Independently reviewed FIRST_FAULT insertion only; exact snippet SHA and unique count.
# The final original whole-module BASE_AST/EXPECTED_BASE_AST below is unchanged.
REVIEWED_FIRST_FAULT_INVERSE = {'controller/cloud_flow.py': [('d27e6a891963716c4d9089909d94d8091282fe74aa5bf64b9174523e2a7067b6',
                               "if budget['execution_mode'] == 'P0_FIRST_FAULT_DIAGNOSTIC':\n"
                               "    roots = reused.get('authority_roots')\n"
                               '    need(type(roots) is list and roots == sorted(set(roots)) and '
                               'all((type(x) is str and P(x).is_absolute() and (P(x) == P(x).resolve()) '
                               "and P(x).is_dir() for x in roots)), 'exact canonical diagnostic "
                               "authority directories')\n"
                               "    need(reused['watch_scope'] == "
                               "'PURE_PROVIDER_FINITE_EVIDENCE_AND_DIAGNOSTIC_AUTHORITY_V1' and "
                               "reused['roots'] == [reused['provider_root'], reused['evidence_root'], "
                               "*roots], 'all actual diagnostic data-authority reads watched')\n"
                               'else:\n'
                               "    need(reused['watch_scope'] == "
                               "'PURE_PROVIDER_AND_FINITE_EVIDENCE_V1' and reused['roots'] == "
                               "[reused['provider_root'], reused['evidence_root']], 'only verified pure "
                               "provider and finite evidence directories watched')",
                               "need(reused['watch_scope'] == 'PURE_PROVIDER_AND_FINITE_EVIDENCE_V1' "
                               "and reused['roots'] == [reused['provider_root'], "
                               "reused['evidence_root']], 'only verified pure provider and finite "
                               "evidence directories watched')"),
                              ['245cefff84c4ba2f20c13e8e0e199e85933483f1945777b9720448410befd236',
                               "if mode in ('BOUNDED_CALIBRATION', 'STAGE_COVERAGE_DIAGNOSTIC', "
                               "'P0_FIRST_FAULT_DIAGNOSTIC'):\n"
                               '    return 2',
                               "if mode in ('BOUNDED_CALIBRATION', 'STAGE_COVERAGE_DIAGNOSTIC'):\n"
                               '    return 2'],
                              ['c22948e731b9daab9e50ecf312e0ba85dfd98e20a42992ecdda5f304037a0e5d',
                               "expected_profiles = {'0'} if b.get('execution_mode') == "
                               "'P0_FIRST_FAULT_DIAGNOSTIC' else set(map(str, range(5)))\n"
                               "if b.get('execution_mode') == 'P0_FIRST_FAULT_DIAGNOSTIC':\n"
                               "    need(admission.get('diagnostic_profiles') == [0], 'fixed "
                               "first-fault profile only')\n"
                               'need(set(cal) == expected_profiles and all((type(x) is int and 0 < x <= '
                               "20000 for x in cal.values())), 'all five explicit unchanged-stimulus "
                               "calibration windows')",
                               'need(set(cal) == set(map(str, range(5))) and all((type(x) is int and 0 '
                               "< x <= 20000 for x in cal.values())), 'all five explicit "
                               "unchanged-stimulus calibration windows')"],
                              ['035fdd66ef45182e2d0fbb7cb3a8080e88f0c753ea8f521bd798cb082fd8021b',
                               "need(candidate and budget['execution_mode'] in "
                               "('STAGE_COVERAGE_DIAGNOSTIC', 'P0_FIRST_FAULT_DIAGNOSTIC'), 'P0 data "
                               "reuse only approved candidate stage diagnostic')",
                               "need(candidate and budget['execution_mode'] == "
                               "'STAGE_COVERAGE_DIAGNOSTIC', 'P0 data reuse only approved candidate "
                               "stage diagnostic')"],
                              ['b50bf1424d19c860ff3d80f360e95c6ebbe6d31e76bc2981c8c143c6f92ca9c2',
                               "need(candidate and budget['execution_mode'] in "
                               "('STAGE_COVERAGE_DIAGNOSTIC', 'P0_FIRST_FAULT_DIAGNOSTIC'), 'reference "
                               "reuse only approved candidate stage')",
                               "need(candidate and budget['execution_mode'] == "
                               "'STAGE_COVERAGE_DIAGNOSTIC', 'reference reuse only approved candidate "
                               "stage')"],
                              ['5b574f725e9c9aa54ec8ebec3649feabc36e7d3de6000affe44efd5d696a6ddf',
                               "candidate = frozen.get('schema') in "
                               "('MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1', "
                               "'MODEL_CANDIDATE_FIRST_FAULT_BUILD_ARTIFACT_V1')",
                               "candidate = frozen.get('schema') == "
                               "'MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1'"],
                              ['dbf5ec991b4ab24d310ccf6ddd9054d44ac075a98f35ed4498387600bec04f2c',
                               'expected_scope = '
                               "'P0_FIRST_FAULT_READONLY_SAME_FULL_M128_STIMULUS_NOT_NUMERICAL_ACCEPTANCE' "
                               "if frozen.get('schema') == "
                               "'MODEL_CANDIDATE_FIRST_FAULT_BUILD_ARTIFACT_V1' else "
                               "'MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL'\n"
                               "need(reviewed['scope'] == expected_scope and "
                               "reviewed['artifact_manifest_sha256'] == "
                               "b['artifact_manifest']['sha256'], 'actual candidate review "
                               "scope/artifact')",
                               "need(reviewed['scope'] == "
                               "'MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL' and "
                               "reviewed['artifact_manifest_sha256'] == "
                               "b['artifact_manifest']['sha256'], 'actual candidate review "
                               "scope/artifact')"],
                              ['1453e2f6ea5dc1ac95b7dd7d46766e56cccefddc9f5a13dc07a3767b64034f24',
                               "if budget['execution_mode'] == 'P0_FIRST_FAULT_DIAGNOSTIC':\n"
                               "    path = D.parent / 'numeric/p0_first_fault_contract.py'\n"
                               "    need(b['pins'].get(str(path)) == sha(path), 'first-fault document "
                               "verifier source pin')\n"
                               "    doc_roots = mod('flow_first_fault_document', "
                               'path).document_roots(b, reviewed)\n'
                               '    imported = dict(imported, first_fault_document_roots=doc_roots)',
                               ''],
                              ['8be16d7dca4bc1f9f6b100a6e8239aa22ad5376df4d5597839350d5363258545',
                               "fields = {k: b[k] for k in ('execution_mode', 'full_block_budget', "
                               "'stage_coverage_budget', 'p0_provider_reuse', 'reference_data_reuse', "
                               "'aggregate_tree_cap_bytes', 'executor_adaptation', 'workspace_loader', "
                               "'retained_materials', 'model_candidate_review') if k in b}\n"
                               "if b.get('execution_mode') == 'P0_FIRST_FAULT_DIAGNOSTIC':\n"
                               "    fields['source_pins'] = b['source_pins']\n"
                               'return fields',
                               "return {k: b[k] for k in ('execution_mode', 'full_block_budget', "
                               "'stage_coverage_budget', 'p0_provider_reuse', 'reference_data_reuse', "
                               "'aggregate_tree_cap_bytes', 'executor_adaptation', 'workspace_loader', "
                               "'retained_materials', 'model_candidate_review') if k in b}"],
                              ['1d9ebde9238c4d20d170f709d4a448eb827e877ef42b09bd04253cb99a027cca',
                               "if b.get('execution_mode') == 'P0_FIRST_FAULT_DIAGNOSTIC':\n"
                               "    need('first_fault_document_roots' in imported, 'first-fault "
                               "metadata verified before watch')\n"
                               "    roots.extend(imported['first_fault_document_roots'])\n"
                               '    roots = list(dict.fromkeys(roots))',
                               '']]}


# Fixed independently reviewed V2 host deltas; not a new historical baseline.

# Fixed source-reviewed V3 delta, layered before the unchanged V2 inverse.

# Exact aggregate-cap layer; every prior inverse and baseline stays unchanged.
REVIEWED_AGGREGATE_CAP_INVERSE = {'controller/cloud_flow.py': [('e3aa1f8d83294c141307ae458d8b6f4891364b5429b5a7393a7bed767841c619',
                               "flow_result = dict(execution_context='CLOUD_EXECUTOR_V1', identity=identity, "
                               'executor_identity=identity, artifact_identity=builder, '
                               "builder_identity=builder, source_pins=b['source_pins'], "
                               "executor_identity_pin=b['executor_identity_pin'], "
                               "builder_handoff=b['builder_handoff'], "
                               "artifact_manifest=b['artifact_manifest'], cloud_budget=b['cloud_budget'], "
                               "execution_approval=b['execution_approval'], job_budget_seconds=limit, "
                               'execution_binding=pin(binding_path), execution_admission=admission, '
                               "execution_mode=admission['mode'], transport_exit_code=code, "
                               'qualification=qualification, execution_policy=execution_policy, '
                               "status=qualification['status'], "
                               "scope='P0_FIRST_FAULT_READONLY_SAME_FULL_M128_STIMULUS_NOT_NUMERICAL_ACCEPTANCE' "
                               "if admission['mode'] == 'P0_FIRST_FAULT_DIAGNOSTIC' else "
                               "'MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL' if "
                               "'model_candidate_review' in b else "
                               "'CHISEL_TEST_GENERATED_SIMULATION_BACKEND_NOT_FINAL_RTL', stages=history, "
                               "retained_materials_scope=imported.get('retained_materials_verified', "
                               "{}).get('scope'), upfront_disk_admission=disk_admission, "
                               'numeric_result=pin(numeric_path), hardware_definitions=1, '
                               'profiles=list(range(5)), uploaded_payloads=False, **{k: b[k] for k in '
                               "('executor_adaptation', 'workspace_loader', 'retained_materials', "
                               "'model_candidate_review', 'p0_provider_reuse', 'reference_data_reuse', "
                               "'aggregate_tree_cap_bytes') if k in b}, "
                               "**dict(stage_coverage_budget=b['stage_coverage_budget'], "
                               "stage_coverage_budget_sha256=b['stage_coverage_budget']['sha256'], "
                               "execution_scope='STAGE_COVERAGE_DIAGNOSTIC_NOT_FULL_ACCEPTANCE') if "
                               "admission['mode'] == 'STAGE_COVERAGE_DIAGNOSTIC' else {})\n"
                               "if 'fullprefill_disk_budget' in budget:\n"
                               '    final_bytes = len((json.dumps(flow_result, indent=2) + '
                               "'\\n').encode('utf-8'))\n"
                               '    need(final_bytes <= '
                               "budget['fullprefill_disk_budget']['shared_output_reservations']['final_evidence_bytes'], "
                               "'finite FULL final evidence fits reviewed reservation')\n"
                               "    final_snapshot = mod('cloud_final_live_budget', "
                               'census_path).census(roots, max_entries=150000, max_seconds=60)\n'
                               "    need(final_snapshot['bytes'] + final_bytes <= tree_cap and "
                               "final_snapshot['free_bytes'] - final_bytes >= 8 << 30, 'finite FULL final "
                               "lifetime bytes and8GiB floor')\n"
                               "save(job / 'FLOW_RESULT.json', flow_result)",
                               'c7b64431c8013d5cce3b29849b80cef0ab40665c836584de248f5cc58b73fa75',
                               "save(job / 'FLOW_RESULT.json', dict(execution_context='CLOUD_EXECUTOR_V1', "
                               'identity=identity, executor_identity=identity, artifact_identity=builder, '
                               "builder_identity=builder, source_pins=b['source_pins'], "
                               "executor_identity_pin=b['executor_identity_pin'], "
                               "builder_handoff=b['builder_handoff'], "
                               "artifact_manifest=b['artifact_manifest'], cloud_budget=b['cloud_budget'], "
                               "execution_approval=b['execution_approval'], job_budget_seconds=limit, "
                               'execution_binding=pin(binding_path), execution_admission=admission, '
                               "execution_mode=admission['mode'], transport_exit_code=code, "
                               'qualification=qualification, execution_policy=execution_policy, '
                               "status=qualification['status'], "
                               "scope='P0_FIRST_FAULT_READONLY_SAME_FULL_M128_STIMULUS_NOT_NUMERICAL_ACCEPTANCE' "
                               "if admission['mode'] == 'P0_FIRST_FAULT_DIAGNOSTIC' else "
                               "'MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL' if "
                               "'model_candidate_review' in b else "
                               "'CHISEL_TEST_GENERATED_SIMULATION_BACKEND_NOT_FINAL_RTL', stages=history, "
                               "retained_materials_scope=imported.get('retained_materials_verified', "
                               "{}).get('scope'), upfront_disk_admission=disk_admission, "
                               'numeric_result=pin(numeric_path), hardware_definitions=1, '
                               'profiles=list(range(5)), uploaded_payloads=False, **{k: b[k] for k in '
                               "('executor_adaptation', 'workspace_loader', 'retained_materials', "
                               "'model_candidate_review', 'p0_provider_reuse', 'reference_data_reuse', "
                               "'aggregate_tree_cap_bytes') if k in b}, "
                               "**dict(stage_coverage_budget=b['stage_coverage_budget'], "
                               "stage_coverage_budget_sha256=b['stage_coverage_budget']['sha256'], "
                               "execution_scope='STAGE_COVERAGE_DIAGNOSTIC_NOT_FULL_ACCEPTANCE') if "
                               "admission['mode'] == 'STAGE_COVERAGE_DIAGNOSTIC' else {}))"),
                              ('6f6ea188db870206049043b2e4a733f2d4a8e7472ff50749c50375f2bd5727fb',
                               "if 'fullprefill_disk_budget' in budget:\n"
                               "    caps['min_free_disk_bytes'] = 8 << 30",
                               '3543b4693a36a1098850b8bc928887694ed59a6deb7d3dfd0339de01f55a77b6',
                               ''),
                              ('061b497c1a36d2d2530ad83751f8c22ed3e9bd08edd2e957bb9411e2450f1fee',
                               'disk_admission = upfront_disk_admission(snapshot, '
                               "P(binding_path).with_name(P(binding_path).name + '.UPFRONT_DISK.json'), "
                               'binding_sha, tree_cap=tree_cap, '
                               "disk_plan=budget.get('fullprefill_disk_budget'))",
                               '830f31807c87421b8f5177d9ca8e4af1391e2d3feac56ffb1b4d1a135cf002e2',
                               'disk_admission = upfront_disk_admission(snapshot, '
                               "P(binding_path).with_name(P(binding_path).name + '.UPFRONT_DISK.json'), "
                               'binding_sha, tree_cap=tree_cap)'),
                              ('d7dfcb07515411fc00161860f598974de872a116b73c5d24fcb46c45356c7be6',
                               'def upfront_disk_admission(snapshot, evidence_path=None, binding_sha=None, '
                               'tree_cap=TREE, disk_plan=None):\n'
                               '    need(type(tree_cap) is int and (tree_cap in (TREE, 12037043872) if '
                               "disk_plan is None else 0 < tree_cap <= TREE), 'explicit reviewed unchanged "
                               "or tighter aggregate cap')\n"
                               '    if disk_plan is not None:\n'
                               "        mod('finite_disk_snapshot', D.parent / "
                               "'cloud_budget.py').fullprefill_disk_snapshot(disk_plan, snapshot, tree_cap)\n"
                               "    need(snapshot.get('schema') == 'SAMPLED_OWNED_LIVE_BYTES_V1' and "
                               "snapshot.get('complete') is True, 'complete upfront watched-root census')\n"
                               "    live = snapshot['bytes']\n"
                               "    free = snapshot['free_bytes']\n"
                               '    need(type(live) is int and 0 <= live <= tree_cap and (type(free) is int) '
                               "and (free >= 0), 'bounded existing watched bytes/free')\n"
                               '    incremental = tree_cap - live\n'
                               '    required = incremental + (8 << 30)\n'
                               '    if evidence_path is not None:\n'
                               '        bounded = lambda v: v if type(v) is int and 0 <= v < 2 ** 64 else '
                               'None\n'
                               '        digest = binding_sha if isinstance(binding_sha, str) and '
                               "len(binding_sha) == 64 and all((c in '0123456789abcdef' for c in "
                               'binding_sha)) else None\n'
                               "        save(evidence_path, dict(schema='CLOUD_UPFRONT_DISK_OBSERVATION_V1', "
                               "scope='SAMPLED_PLANNING_ONLY_PHASE_GATES_UNCHANGED', binding_sha256=digest, "
                               "census_schema='SAMPLED_OWNED_LIVE_BYTES_V1', census_complete=True, "
                               'existing_watched_bytes=bounded(live), '
                               'maximum_additional_bytes=bounded(incremental), free_reserve_bytes=8 << 30, '
                               'required_free_bytes=bounded(required), observed_free_bytes=bounded(free), '
                               'shortfall_bytes=bounded(max(0, required - free)), '
                               "status='SUFFICIENT_SAMPLED_SPACE' if free >= required else "
                               "'REJECTED_INSUFFICIENT_SAMPLED_SPACE', numerical_pass=False, "
                               'job_created=False))\n'
                               "    need(free >= required, 'remaining aggregate growth plus unchanged "
                               "free8GiB')\n"
                               '    return dict(existing_watched_bytes=live, '
                               'maximum_additional_bytes=incremental, free_reserve_bytes=8 << 30, '
                               'required_free_bytes=required, observed_free_bytes=free, '
                               "scope='SAMPLED_PLANNING_ONLY_PHASE_GATES_UNCHANGED')",
                               '954b92e949a5a5de0717163fad52e1f92e5c85402d5e1bc4e7c9859a8748fd1a',
                               'def upfront_disk_admission(snapshot, evidence_path=None, binding_sha=None, '
                               'tree_cap=TREE):\n'
                               '    need(type(tree_cap) is int and tree_cap in (TREE, 12037043872), '
                               "'explicit reviewed unchanged or tighter aggregate cap')\n"
                               "    need(snapshot.get('schema') == 'SAMPLED_OWNED_LIVE_BYTES_V1' and "
                               "snapshot.get('complete') is True, 'complete upfront watched-root census')\n"
                               "    live = snapshot['bytes']\n"
                               "    free = snapshot['free_bytes']\n"
                               '    need(type(live) is int and 0 <= live <= tree_cap and (type(free) is int) '
                               "and (free >= 0), 'bounded existing watched bytes/free')\n"
                               '    incremental = tree_cap - live\n'
                               '    required = incremental + (8 << 30)\n'
                               '    if evidence_path is not None:\n'
                               '        bounded = lambda v: v if type(v) is int and 0 <= v < 2 ** 64 else '
                               'None\n'
                               '        digest = binding_sha if isinstance(binding_sha, str) and '
                               "len(binding_sha) == 64 and all((c in '0123456789abcdef' for c in "
                               'binding_sha)) else None\n'
                               "        save(evidence_path, dict(schema='CLOUD_UPFRONT_DISK_OBSERVATION_V1', "
                               "scope='SAMPLED_PLANNING_ONLY_PHASE_GATES_UNCHANGED', binding_sha256=digest, "
                               "census_schema='SAMPLED_OWNED_LIVE_BYTES_V1', census_complete=True, "
                               'existing_watched_bytes=bounded(live), '
                               'maximum_additional_bytes=bounded(incremental), free_reserve_bytes=8 << 30, '
                               'required_free_bytes=bounded(required), observed_free_bytes=bounded(free), '
                               'shortfall_bytes=bounded(max(0, required - free)), '
                               "status='SUFFICIENT_SAMPLED_SPACE' if free >= required else "
                               "'REJECTED_INSUFFICIENT_SAMPLED_SPACE', numerical_pass=False, "
                               'job_created=False))\n'
                               "    need(free >= required, 'remaining aggregate growth plus unchanged "
                               "free8GiB')\n"
                               '    return dict(existing_watched_bytes=live, '
                               'maximum_additional_bytes=incremental, free_reserve_bytes=8 << 30, '
                               'required_free_bytes=required, observed_free_bytes=free, '
                               "scope='SAMPLED_PLANNING_ONLY_PHASE_GATES_UNCHANGED')")]}
PRE_AGGREGATE_AST_SHA256 = {'controller/cloud_flow.py': '8b0ded17c7ffbeddd6d098ca6ca90e883606232c9be8e4ad48ff9f2c07a28bed'}

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

REVIEWED_V3_INVERSE = {'controller/cloud_flow.py': [('ae46be8c44f19e9f505128b511499d6089c69065b3f80270e111ff1514aac0ef',
                               "if admission.get('budget_version') in (2, 3):\n"
                               "    path = D.parent / 'execution_mode.py'\n"
                               "    need(pins.get(str(path)) == sha(path), 'V2 parent CPU verifier source "
                               "pin')\n"
                               "    parent_cpu_policy = mod('cloud_full_parent_cpu', "
                               'path).install_full_v2_parent_cpu_limit(admission, limit)',
                               '31df4786460a13ca6bcd1e1569bc32267407633159107cb034efa18f34cd09d4',
                               "if admission.get('budget_version') == 2:\n"
                               "    path = D.parent / 'execution_mode.py'\n"
                               "    need(pins.get(str(path)) == sha(path), 'V2 parent CPU verifier source "
                               "pin')\n"
                               "    parent_cpu_policy = mod('cloud_full_parent_cpu', "
                               'path).install_full_v2_parent_cpu_limit(admission, limit)',
                               17),
                              ('e7ca15582c3173b52ab729169a3d0f1153af3265e3fdd37036dbeb4523e85691',
                               "if admission.get('budget_version') == 3:\n"
                               '    expected_profiles = set(map(str, '
                               'verifier.ready_queue_profiles(admission)))',
                               '3543b4693a36a1098850b8bc928887694ed59a6deb7d3dfd0339de01f55a77b6',
                               '',
                               16)]}
PRE_V3_AST_SHA256 = {'controller/cloud_flow.py': 'a3464884eb5ee27b7122c74541741e47d6295b9c80af2589b209aebd2941469e'}

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

REVIEWED_V2_INVERSE = {'controller/cloud_flow.py': [('9f04a054f91ce500ad5d6277b1e105e493cc09729e298596873e16c9d8c54848',
                               'ceiling = 20000\n'
                               "if 'budget_version' in admission:\n"
                               "    path = D.parent / 'execution_mode.py'\n"
                               "    need(b['pins'].get(str(path)) == sha(path), 'V2 reservation verifier "
                               "source pin')\n"
                               "    verifier = mod('cloud_full_watchdog_reservation', path)\n"
                               '    ceiling = verifier.profile_wall_ceiling(admission)\n'
                               'need(set(cal) == expected_profiles and all((type(x) is int and 0 < x <= '
                               "ceiling for x in cal.values())), 'all five explicit unchanged-stimulus "
                               "execution windows')",
                               '41388bf815a5772dd357ae6aa91566e622efe11bffa7cb2fe34a072ad2c9f92d',
                               'need(set(cal) == expected_profiles and all((type(x) is int and 0 < x <= '
                               "20000 for x in cal.values())), 'all five explicit unchanged-stimulus "
                               "calibration windows')"),
                              ('20f253392ccd25b4c799dc13acd332db73df8afeff791b21465d3b39f013f73b',
                               "reserved = verifier.profile_reserved_seconds(admission) if 'budget_version' "
                               'in admission else cal\n'
                               "tail = sum(reserved.values()) + 7 * q['provider'] + 11 * 120 + 1530 + "
                               "q['parent']",
                               '72ccda91da816d092ffa247de9115e7e2ccf91126607226c4c87f5cf23cbb1f9',
                               "tail = sum(cal.values()) + 7 * q['provider'] + 11 * 120 + 1530 + "
                               "q['parent']"),
                              ('36d956d6c1ec7b5bc58a43f89983d5c1d3b213dafc4fb52bca15f69d64f6eb33',
                               'roots = list(dict.fromkeys([str(job), str(repo), '
                               "*[str(P(b[k]['path']).parent) for k in ('artifact_manifest', "
                               "'builder_handoff', 'executor_identity_pin', 'cloud_budget', "
                               "'execution_approval', 'executor_adaptation', 'workspace_loader', "
                               "'retained_materials', 'model_candidate_review', 'stage_coverage_budget', "
                               "'full_block_budget') if b.get(k) is not None]]))",
                               '1009a961dc429317db183e83665aed262217b25b2eb70ba7f20ac0bb02b45ebe',
                               'roots = list(dict.fromkeys([str(job), str(repo), '
                               "*[str(P(b[k]['path']).parent) for k in ('artifact_manifest', "
                               "'builder_handoff', 'executor_identity_pin', 'cloud_budget', "
                               "'execution_approval', 'executor_adaptation', 'workspace_loader', "
                               "'retained_materials', 'model_candidate_review', 'stage_coverage_budget') if "
                               'k in b]]))'),
                              ('27e3a2b0bb103d898e609ebc3ac093d05e7e3ee394f83348b3d802b015c21d3c',
                               "if b.get('full_block_budget') is not None:\n"
                               "    full_doc = json.loads(P(b['full_block_budget']['path']).read_text())\n"
                               "    for evidence in full_doc['basis'].values():\n"
                               "        parent = str(P(evidence['path']).parent)\n"
                               '        if parent not in roots:\n'
                               '            roots.append(parent)',
                               '3543b4693a36a1098850b8bc928887694ed59a6deb7d3dfd0339de01f55a77b6',
                               ''),
                              ('6dc47e62ce796f55c05eb733d9020fc2d952701b9569f01b1431850e8d2a9530',
                               'parent_cpu_policy = None\n'
                               "if admission.get('budget_version') == 2:\n"
                               "    path = D.parent / 'execution_mode.py'\n"
                               "    need(pins.get(str(path)) == sha(path), 'V2 parent CPU verifier source "
                               "pin')\n"
                               "    parent_cpu_policy = mod('cloud_full_parent_cpu', "
                               'path).install_full_v2_parent_cpu_limit(admission, limit)',
                               '3543b4693a36a1098850b8bc928887694ed59a6deb7d3dfd0339de01f55a77b6',
                               ''),
                              ('1ec9f7313f129e63fb0099489ff82bd709657574b5620bd39006e795e1aba125',
                               'if parent_cpu_policy is not None:\n'
                               "    save(job / 'bindings/FULL_V2_PARENT_CPU_LIMIT.json', parent_cpu_policy)",
                               '3543b4693a36a1098850b8bc928887694ed59a6deb7d3dfd0339de01f55a77b6',
                               '')]}
PRE_V2_AST_SHA256 = {'controller/cloud_flow.py': 'c13b49f746d533261dcb0debf381364bdf9c717ce81cbe876fe4a9c2c559f90d'}

def undo_reviewed_v2_delta(test,tree,relative):
 # Exact reviewed V2 host fragments only. This inverse runs before all historical
 # inverses and before constructing their mutation/duplicate fixtures.
 import copy
 tree=copy.deepcopy(tree)
 for digest,new_text,old_digest,old_text in REVIEWED_V2_INVERSE.get(relative,()):
  want=ast.parse(new_text).body;replacement=ast.parse(old_text).body
  fingerprint=lambda body:hashlib.sha256(ast.dump(ast.Module(body=body,type_ignores=[]),include_attributes=False).encode()).hexdigest()
  test.assertEqual(fingerprint(want),digest,'fixed reviewed V2 fragment')
  test.assertEqual(fingerprint(replacement),old_digest,'fixed pre-V2 replacement')
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
  test.assertEqual(len(matches),1,'one exact reviewed V2 fragment: '+digest)
  container,index=matches[0];container[index:index+len(want)]=copy.deepcopy(replacement)
 return tree

FIRST_FAULT_FLOW_SCOPE_EXPRESSION="'P0_FIRST_FAULT_READONLY_SAME_FULL_M128_STIMULUS_NOT_NUMERICAL_ACCEPTANCE' if admission['mode'] == 'P0_FIRST_FAULT_DIAGNOSTIC' else 'MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL' if 'model_candidate_review' in b else 'CHISEL_TEST_GENERATED_SIMULATION_BACKEND_NOT_FINAL_RTL'"
FIRST_FAULT_FLOW_SCOPE_AST_SHA256='7c1de0423b45634c9b1ee7f4cbf706794aab8548086ebd0125f124a231ac3f93'
def undo_first_fault_flow_scope(test,tree):
 import copy
 wanted=ast.parse(FIRST_FAULT_FLOW_SCOPE_EXPRESSION,mode='eval').body
 expected=ast.dump(wanted,include_attributes=False)
 test.assertEqual(hashlib.sha256(expected.encode()).hexdigest(),FIRST_FAULT_FLOW_SCOPE_AST_SHA256)
 hits=[]
 class ExactScope(ast.NodeTransformer):
  def visit_IfExp(self,node):
   if ast.dump(node,include_attributes=False)==expected:
    hits.append(True);return copy.deepcopy(wanted.orelse)
   return self.generic_visit(node)
 tree=ExactScope().visit(tree)
 test.assertEqual(len(hits),1,'one exact reviewed FLOW scope IfExp')
 return tree

def undo_reviewed_first_fault_delta(test,tree,relative):
 if relative=='controller/cloud_flow.py':tree=undo_first_fault_flow_scope(test,tree)
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

class Tests(unittest.TestCase):
 def snap(self,free):return dict(schema='SAMPLED_OWNED_LIVE_BYTES_V1',complete=True,bytes=4<<30,free_bytes=free,roots=['SECRET_PAYLOAD_PATH'],error='SECRET_ERROR')
 def test_insufficient_prelaunch_saved_before_original_rejection(self):
  with tempfile.TemporaryDirectory()as t:
   root=pathlib.Path(t);receipt=root/'BINDING.json.UPFRONT_DISK.json';required=f.TREE-(4<<30)+(8<<30)
   with self.assertRaisesRegex(ValueError,'remaining aggregate growth plus unchanged free8GiB'):f.upfront_disk_admission(self.snap(required-3109000000),receipt,'a'*64)
   r=json.loads(receipt.read_text());self.assertEqual(r['shortfall_bytes'],3109000000);self.assertEqual(r['required_free_bytes'],required);self.assertFalse(r['job_created']);self.assertEqual(list(root.iterdir()),[receipt]);self.assertNotIn('SECRET',receipt.read_text());self.assertLess(receipt.stat().st_size,2048)
 def test_success_return_unchanged_and_exclusive_receipt(self):
  with tempfile.TemporaryDirectory()as t:
   receipt=pathlib.Path(t)/'disk.json';snapshot=self.snap(20<<30);original=f.upfront_disk_admission(snapshot);self.assertEqual(f.upfront_disk_admission(snapshot,receipt,'b'*64),original)
   self.assertEqual(json.loads(receipt.read_text())['shortfall_bytes'],0)
   with self.assertRaises(FileExistsError):f.upfront_disk_admission(snapshot,receipt,'b'*64)
 def test_invalid_snapshot_original_gate_before_receipt(self):
  for edit in ({'complete':False},{'bytes':True},{'bytes':f.TREE+1},{'free_bytes':-1}):
   with self.subTest(edit=edit),tempfile.TemporaryDirectory()as t:
    receipt=pathlib.Path(t)/'disk.json'
    with self.assertRaises(ValueError):f.upfront_disk_admission(dict(self.snap(20<<30),**edit),receipt,'c'*64)
    self.assertFalse(receipt.exists())
 def test_local_receipt_is_bounded_and_does_not_change_gate(self):
  with tempfile.TemporaryDirectory()as t:
   receipt=pathlib.Path(t)/'disk.json';snap=self.snap(2**10000)
   self.assertEqual(f.upfront_disk_admission(snap,receipt,'secret'),f.upfront_disk_admission(snap));r=json.loads(receipt.read_text());self.assertIsNone(r['observed_free_bytes']);self.assertIsNone(r['binding_sha256']);self.assertLess(receipt.stat().st_size,2048)
 def test_actual_call_is_binding_sibling_before_job_creation(self):
  text=(D/'controller/cloud_flow.py').read_text();self.assertIn("P(binding_path).with_name(P(binding_path).name+'.UPFRONT_DISK.json'),binding_sha",text);self.assertLess(text.index(' disk_admission=upfront_disk_admission('),text.index(' job.mkdir()'))
 def test_only_diagnostic_delta_ast(self):
  self.check_original_ast(undo_reviewed_v3_delta(self,undo_reviewed_aggregate_cap_delta(self,ast.parse((D/'controller/cloud_flow.py').read_text()),'controller/cloud_flow.py'),'controller/cloud_flow.py'))
 def check_original_ast(self,tree):
  tree=undo_reviewed_v2_delta(self,tree,'controller/cloud_flow.py')
  tree=undo_reviewed_stage_delta(self,tree,'controller/cloud_flow.py')
  definitions=[n for n in ast.walk(tree)if isinstance(n,ast.FunctionDef)and n.name=='upfront_disk_admission']
  calls=[n for n in ast.walk(tree)if isinstance(n,ast.Call)and isinstance(n.func,ast.Name)and n.func.id=='upfront_disk_admission']
  conditions=[n for n in ast.walk(tree)if isinstance(n,ast.If)and ast.unparse(n.test)=='evidence_path is not None']
  self.assertEqual(len(definitions),1);self.assertEqual(len(calls),1);self.assertEqual(len(conditions),1)
  function=definitions[0];call=calls[0];diagnostic=conditions[0]
  self.assertIn(diagnostic,function.body)
  self.assertEqual(ast.unparse(function.args),'snapshot, evidence_path=None, binding_sha=None')
  self.assertEqual(ast.unparse(call),"upfront_disk_admission(snapshot, P(binding_path).with_name(P(binding_path).name + '.UPFRONT_DISK.json'), binding_sha)")
  self.assertEqual(hashlib.sha256(ast.dump(diagnostic,include_attributes=False).encode()).hexdigest(),'c3bb48f0d043a3b02d43bfb69ab5a0a77a81b9938434cde2e836b573d72ba9ad')
  function.args.args=function.args.args[:1];function.args.defaults=[];function.body.remove(diagnostic);call.args=call.args[:1]
  self.assertEqual(hashlib.sha256(ast.dump(tree,include_attributes=False).encode()).hexdigest(),EXPECTED_BASE_AST)
class InverseNegativeTests(unittest.TestCase):
 def test_reviewed_delta_mutation_and_duplicate_rejected(self):
  for relative,rows in REVIEWED_STAGE_INVERSE.items():
   root=D.parent if D.name=='numeric'else D
   original=undo_reviewed_v2_delta(self,undo_reviewed_v3_delta(self,undo_reviewed_aggregate_cap_delta(self,ast.parse((root/relative).read_text()),relative),relative),relative)
   # An additional copy cannot silently disappear: unique match count must fail.
   duplicate=undo_reviewed_v2_delta(self,undo_reviewed_v3_delta(self,undo_reviewed_aggregate_cap_delta(self,ast.parse((root/relative).read_text()),relative),relative),relative);duplicate.body.extend(ast.parse(rows[0][1]).body)
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
   original=undo_reviewed_v2_delta(self,undo_reviewed_v3_delta(self,undo_reviewed_aggregate_cap_delta(self,ast.parse((root/relative).read_text()),relative),relative),relative)
   duplicate=undo_reviewed_v2_delta(self,undo_reviewed_v3_delta(self,undo_reviewed_aggregate_cap_delta(self,ast.parse((root/relative).read_text()),relative),relative),relative);duplicate.body.extend(ast.parse(rows[0][1]).body)
   with self.subTest(relative=relative,case='duplicate'),self.assertRaises(AssertionError):undo_reviewed_reference_delta(self,duplicate,relative)
   hit=False
   for n in ast.walk(original):
    if isinstance(n,ast.Constant)and n.value=='reference_data_reuse':n.value='UNREVIEWED_REFERENCE_REUSE';hit=True
   self.assertTrue(hit)
   with self.subTest(relative=relative,case='changed gate'),self.assertRaises(AssertionError):undo_reviewed_reference_delta(self,original,relative)


class FirstFaultInverseNegativeTests(unittest.TestCase):
 def test_exact_first_fault_snippets_changed_or_duplicate_fail(self):
  import copy
  for relative,rows in REVIEWED_FIRST_FAULT_INVERSE.items():
   raw=(D/relative).read_text();normalized=undo_reviewed_v2_delta(self,undo_reviewed_v3_delta(self,undo_reviewed_aggregate_cap_delta(self,ast.parse(raw),relative),relative),relative)
   for digest,new_text,old_text in rows:
    duplicate=copy.deepcopy(normalized);duplicate.body.extend(ast.parse(new_text).body)
    with self.subTest(relative=relative,digest=digest,case='duplicate'),self.assertRaises(AssertionError):undo_reviewed_first_fault_delta(self,duplicate,relative)
   changed=copy.deepcopy(normalized);hits=0
   for n in ast.walk(changed):
    if isinstance(n,ast.Constant)and n.value=='P0_FIRST_FAULT_DIAGNOSTIC':n.value='UNREVIEWED_FIRST_FAULT';hits+=1
    elif isinstance(n,ast.Attribute)and n.attr=='FIRST_FAULT':n.attr='UNREVIEWED_FIRST_FAULT';hits+=1
   self.assertGreater(hits,0)
   with self.subTest(relative=relative,case='changed gate'),self.assertRaises(AssertionError):undo_reviewed_first_fault_delta(self,changed,relative)

class FlowScopeInverseNegativeTests(unittest.TestCase):
 def test_duplicate_scope_rejected(self):
  tree=ast.parse('x='+FIRST_FAULT_FLOW_SCOPE_EXPRESSION+'\ny='+FIRST_FAULT_FLOW_SCOPE_EXPRESSION)
  with self.assertRaises(AssertionError):undo_first_fault_flow_scope(self,tree)
 def test_mutated_scope_rejected(self):
  tree=ast.parse('x='+FIRST_FAULT_FLOW_SCOPE_EXPRESSION.replace('P0_FIRST_FAULT_DIAGNOSTIC','UNREVIEWED_MODE'))
  with self.assertRaises(AssertionError):undo_first_fault_flow_scope(self,tree)


class V2InverseNegativeTests(unittest.TestCase):
 def test_v2_restores_exact_pre_v2_source_ast(self):
  for relative,wanted in PRE_V2_AST_SHA256.items():
   tree=undo_reviewed_v2_delta(self,undo_reviewed_v3_delta(self,undo_reviewed_aggregate_cap_delta(self,ast.parse((D/relative).read_text()),relative),relative),relative)
   with self.subTest(relative=relative):self.assertEqual(hashlib.sha256(ast.dump(tree,include_attributes=False).encode()).hexdigest(),wanted)
 def test_each_v2_fragment_missing_mutated_or_duplicated_is_rejected(self):
  import copy
  for relative,rows in REVIEWED_V2_INVERSE.items():
   for digest,new_text,old_digest,old_text in rows:
    want=ast.parse(new_text).body;want_dump=[ast.dump(n,include_attributes=False)for n in want]
    for case in ('missing','mutated','duplicate'):
     tree=undo_reviewed_v3_delta(self,undo_reviewed_aggregate_cap_delta(self,ast.parse((D/relative).read_text()),relative),relative);hits=[]
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
      self.assertTrue(names);names[0].id='UNREVIEWED_V2_MUTATION'
     with self.subTest(relative=relative,digest=digest,case=case),self.assertRaises(AssertionError):undo_reviewed_v2_delta(self,tree,relative)
 def test_unrelated_caller_delta_survives_inverse_and_fails_old_baseline(self):
  for relative in PRE_V2_AST_SHA256:
   tree=undo_reviewed_v3_delta(self,undo_reviewed_aggregate_cap_delta(self,ast.parse((D/relative).read_text()),relative),relative);tree.body.extend(ast.parse('UNREVIEWED_CALLER_DELTA = 1').body)
   before=ast.dump(tree,include_attributes=False)
   restored=undo_reviewed_v2_delta(self,tree,relative)
   self.assertEqual(ast.dump(tree,include_attributes=False),before,'V2 inverse preserves its caller input')
   self.assertIn('UNREVIEWED_CALLER_DELTA',ast.unparse(restored))
   with self.subTest(relative=relative),self.assertRaises(AssertionError)as caught:Tests().check_original_ast(tree)
   self.assertIn(EXPECTED_BASE_AST,str(caught.exception),'unrelated delta fails the unchanged historical AST hash')
   self.assertNotIn('one exact reviewed V2 fragment',str(caught.exception))


class V3InverseNegativeTests(unittest.TestCase):
 def test_v3_restores_exact_frozen_v2_source_ast(self):
  for relative,wanted in PRE_V3_AST_SHA256.items():
   tree=undo_reviewed_v3_delta(self,undo_reviewed_aggregate_cap_delta(self,ast.parse((D/relative).read_text()),relative),relative)
   with self.subTest(relative=relative):self.assertEqual(hashlib.sha256(ast.dump(tree,include_attributes=False).encode()).hexdigest(),wanted)
 def test_each_v3_fragment_missing_mutated_or_duplicated_is_rejected(self):
  import copy
  for relative,rows in REVIEWED_V3_INVERSE.items():
   self.assertEqual([row[4]for row in rows],sorted((row[4]for row in rows),reverse=True),'reverse reviewed author order')
   for digest,new_text,old_digest,old_text,author_index in rows:
    want=ast.parse(new_text).body;want_dump=[ast.dump(n,include_attributes=False)for n in want]
    for case in ('missing','mutated','duplicate'):
     tree=undo_reviewed_aggregate_cap_delta(self,ast.parse((D/relative).read_text()),relative);hits=[]
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
     with self.subTest(relative=relative,author_index=author_index,case=case),self.assertRaisesRegex(AssertionError,'one exact reviewed V3 fragment: '+digest):undo_reviewed_v3_delta(self,tree,relative)
 def test_unrelated_caller_delta_reaches_unchanged_historical_baseline(self):
  for relative in PRE_V3_AST_SHA256:
   tree=undo_reviewed_aggregate_cap_delta(self,ast.parse((D/relative).read_text()),relative);tree.body.extend(ast.parse('UNREVIEWED_V3_CALLER_DELTA = 1').body)
   before=ast.dump(tree,include_attributes=False);restored=undo_reviewed_v3_delta(self,tree,relative)
   self.assertEqual(ast.dump(tree,include_attributes=False),before,'V3 inverse preserves its caller input')
   self.assertIn('UNREVIEWED_V3_CALLER_DELTA',ast.unparse(restored))
   with self.subTest(relative=relative),self.assertRaises(AssertionError)as caught:Tests().check_original_ast(restored)
   self.assertIn(EXPECTED_BASE_AST,str(caught.exception),'unrelated delta fails original historical AST hash')
   self.assertNotIn('one exact reviewed V3 fragment',str(caught.exception))
   self.assertNotIn('one exact reviewed V2 fragment',str(caught.exception))


class AggregateCapInverseTests(unittest.TestCase):
 def test_aggregate_restores_exact_prior_source_ast(self):
  for relative,wanted in PRE_AGGREGATE_AST_SHA256.items():
   restored=undo_reviewed_aggregate_cap_delta(self,ast.parse((D/relative).read_text()),relative)
   with self.subTest(relative=relative):self.assertEqual(hashlib.sha256(ast.dump(restored,include_attributes=False).encode()).hexdigest(),wanted)
 def test_each_aggregate_fragment_missing_mutated_or_duplicated_rejected(self):
  import copy
  for relative,rows in REVIEWED_AGGREGATE_CAP_INVERSE.items():
   for digest,new_text,old_digest,old_text in rows:
    want=ast.parse(new_text).body;want_dump=[ast.dump(n,include_attributes=False)for n in want]
    for case in ('missing','mutated','duplicate'):
     tree=copy.deepcopy(ast.parse((D/relative).read_text()));hits=[]
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
   tree=copy.deepcopy(ast.parse((D/relative).read_text()));tree.body.extend(ast.parse('UNREVIEWED_AGGREGATE_CALLER_DELTA = 1').body)
   before=ast.dump(tree,include_attributes=False);restored=undo_reviewed_aggregate_cap_delta(self,tree,relative)
   self.assertEqual(ast.dump(tree,include_attributes=False),before,'aggregate inverse preserves input')
   self.assertIn('UNREVIEWED_AGGREGATE_CALLER_DELTA',ast.unparse(restored))
   with self.subTest(relative=relative),self.assertRaises(AssertionError)as caught:Tests().check_original_ast(undo_reviewed_v3_delta(self,restored,relative))
   self.assertIn(EXPECTED_BASE_AST,str(caught.exception),'original historical hash is rejection reason')
   self.assertNotIn('one exact aggregate-cap fragment',str(caught.exception))
   self.assertNotIn('one exact finite-log fragment',str(caught.exception))
   self.assertNotIn('one exact reviewed V3 fragment',str(caught.exception))

if __name__=='__main__':unittest.main()
