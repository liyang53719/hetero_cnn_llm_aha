"""Light file-only diagnostics; no census, job, supervisor or DUT execution."""
import ast,hashlib,importlib.util,json,pathlib,tempfile,unittest
D=pathlib.Path(__file__).resolve().parent
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
def undo_reviewed_reference_delta(test,tree,relative):
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
  tree=ast.parse((D/'controller/cloud_flow.py').read_text())
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
   original=ast.parse((root/relative).read_text())
   # An additional copy cannot silently disappear: unique match count must fail.
   duplicate=ast.parse((root/relative).read_text());duplicate.body.extend(ast.parse(rows[0][1]).body)
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
   original=ast.parse((root/relative).read_text())
   duplicate=ast.parse((root/relative).read_text());duplicate.body.extend(ast.parse(rows[0][1]).body)
   with self.subTest(relative=relative,case='duplicate'),self.assertRaises(AssertionError):undo_reviewed_reference_delta(self,duplicate,relative)
   hit=False
   for n in ast.walk(original):
    if isinstance(n,ast.Constant)and n.value=='reference_data_reuse':n.value='UNREVIEWED_REFERENCE_REUSE';hit=True
   self.assertTrue(hit)
   with self.subTest(relative=relative,case='changed gate'),self.assertRaises(AssertionError):undo_reviewed_reference_delta(self,original,relative)

if __name__=='__main__':unittest.main()
