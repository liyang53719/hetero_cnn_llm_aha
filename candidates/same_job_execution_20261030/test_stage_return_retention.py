"""Local return persistence only. No subprocess, DUT or real runtime import."""
import ast,hashlib,json,pathlib,tempfile,types,unittest
import os
D=pathlib.Path(os.environ.get('FIRST_FAULT_LEGACY_TEST_SOURCE',str(pathlib.Path(__file__).resolve().parent))).resolve()
# Candidate flow/tail branches independently reviewed 2026-11-01; not a save-only delta.
BASE_AST={'controller/cloud_flow.py': '1d5f8f80511850394a4d8bb0bd2744c0ba3dfae82a6a98c65d981ded2691f9e4', 'controller/flow.py': '6640f4a848fc6cbc4300bb774c6d1e8e6ed8f055c29cc23e868cfc73ceaccfcf', 'numeric/numeric_tail.py': '4946ee900cd42024fd0f4e6c7589b29671fbc4b258c3a31906741c4e3bbb6232'}
EXPECTED={
 'controller/cloud_flow.py':"save(job / 'bindings' / (name + '_SUPERVISOR_RETURN.json'), r)",
 'controller/flow.py':"save(job / 'bindings' / (name + '_SUPERVISOR_RETURN.json'), r)",
 'numeric/numeric_tail.py':"save(out / 'phases' / (name + '_SUPERVISOR_RETURN.json'), r)",
}
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
                               "'model_candidate_review') if k in b}))")],
 'numeric/numeric_tail.py': [('bdcea0b9485bc538800ae32c592d6a6c4249b1a1913f741bbccbe3a540492a0c',
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
                               "admission['mode'] == 'STAGE_COVERAGE_DIAGNOSTIC' else {}))")],
 'numeric/numeric_tail.py': [('ff7ac986fb69d6c04a1e20365c402d0823a056f0c4c5c3d01b69e40972a6ba2a',
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
                               '']],
 'numeric/numeric_tail.py': [['8b36c4832459be16aca77c6b2673700334ee3d491b543b60a5b52e283f99a9c8',
                              "if b.get('reference_data_reuse') is not None:\n"
                              "    need(b['execution_mode'] in (execution_mode.STAGE, "
                              "execution_mode.FIRST_FAULT) and b.get('model_candidate_review') is not "
                              "None, 'reference reuse only approved candidate stage coverage')\n"
                              "if b.get('p0_provider_reuse') is not None:\n"
                              "    need(b['execution_mode'] in (execution_mode.STAGE, "
                              "execution_mode.FIRST_FAULT) and b.get('model_candidate_review') is not "
                              "None, 'P0 reuse only approved candidate stage coverage')",
                              "if b.get('reference_data_reuse') is not None:\n"
                              "    need(b['execution_mode'] == execution_mode.STAGE and "
                              "b.get('model_candidate_review') is not None, 'reference reuse only "
                              "approved candidate stage coverage')\n"
                              "if b.get('p0_provider_reuse') is not None:\n"
                              "    need(b['execution_mode'] == execution_mode.STAGE and "
                              "b.get('model_candidate_review') is not None, 'P0 reuse only approved "
                              "candidate stage coverage')"],
                             ['f9c4ab85ba0089d2b0f20c27f6d1100e098a01f281b797543b8b43c3899136a8',
                              "need(cloud is not None and b['execution_mode'] in (execution_mode.STAGE, "
                              "execution_mode.FIRST_FAULT) and (b['tree_cap'] == 12037043872), 'exact "
                              "reference-data-only tree reduction')",
                              "need(cloud is not None and b['execution_mode'] == execution_mode.STAGE "
                              "and (b['tree_cap'] == 12037043872), 'exact reference-data-only tree "
                              "reduction')"],
                             ['e14a233fa3cbed06c5f25b4a1b5d3f0214ef465710c57813a1b7ab1104184093',
                              'def execution_profiles(b, admission):\n'
                              '    selected = profile_policy.eligible(b)\n'
                              "    if admission['mode'] == execution_mode.FIRST_FAULT:\n"
                              '        need(selected == list(range(5)) and '
                              "admission.get('diagnostic_profiles') == [0] and "
                              "(type(admission['diagnostic_profiles'][0]) is int), 'registered hardware "
                              "unchanged; only integer P0 selected')\n"
                              '        return [0]\n'
                              '    return selected',
                              ''],
                             ['7fca2d91ad540d1a312208082b2e0ec8243754ee2ef394a7adfbf6f1ae694ce2',
                              "if admission['mode'] == execution_mode.FIRST_FAULT:\n"
                              "    need(profile == 0 and admission.get('diagnostic_profiles') == [0] "
                              "and (b.get('execution_context') == 'CLOUD_EXECUTOR_V1') and "
                              "(b.get('full_block_budget') is None) and (b.get('stage_coverage_budget') "
                              "is None), 'only approved P0 first-fault diagnostic')\n"
                              "elif admission['mode'] == execution_mode.STAGE:\n"
                              "    need(b.get('execution_context') == 'CLOUD_EXECUTOR_V1' and "
                              "b.get('full_block_budget') is None, 'stage coverage is cloud-only, not "
                              "full acceptance')\n"
                              "    budget = b['stage_coverage_budget']\n"
                              "    argv += ['--stage-coverage-budget', budget['path'], "
                              "'--stage-coverage-budget-sha256', budget['sha256']]\n"
                              'else:\n'
                              "    need(admission['mode'] == execution_mode.FULL, 'explicit execution "
                              "mode')\n"
                              "    budget = b['full_block_budget']\n"
                              "    argv += ['--full-block-budget', budget['path'], "
                              "'--full-block-budget-sha256', budget['sha256']]",
                              "if admission['mode'] == execution_mode.STAGE:\n"
                              "    need(b.get('execution_context') == 'CLOUD_EXECUTOR_V1' and "
                              "b.get('full_block_budget') is None, 'stage coverage is cloud-only, not "
                              "full acceptance')\n"
                              "    budget = b['stage_coverage_budget']\n"
                              "    argv += ['--stage-coverage-budget', budget['path'], "
                              "'--stage-coverage-budget-sha256', budget['sha256']]\n"
                              'else:\n'
                              "    need(admission['mode'] == execution_mode.FULL, 'explicit execution "
                              "mode')\n"
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
                              "runtime['receipt']['sha256'] and ref_doc['runtime_source_pins_sha256'] "
                              "== runtime['sidecar']['sha256'], 'reference matches actual selected "
                              "installed runtime/sidecar')\n"
                              '\n'
                              '        def provider_stage(label, argv):\n'
                              "            return stage(f'p{i}_{label}', argv, lease_out=lease_root)\n"
                              "        initialization = out / 'phases' / f'p{i}_initialize_input.json'\n"
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
                              "'provider_from_frozen.py'), '--initialize-binding', str(initialization), "
                              "'--sha256', sha(initialization)], 120, lease_out=lease_root)\n"
                              "        material.prepare(b['repo'], b['materializer'], profile, i, "
                              "runtime['wrapper'], b['payload'], b['references'][str(i)], "
                              "provider_stage, pins, p0_provider_reuse=b.get('p0_provider_reuse') if i "
                              '== 0 else None)\n'
                              "        stage(f'p{i}_connect', [b['python'], '-B', str(D / "
                              "'connect_owned.py'), '--existing-output', str(profile), '--profile', "
                              'str(i), *identity_args], 120, lease_out=lease_root)\n'
                              '        generated = json.loads((profile / '
                              "'CONSUMER_ARGV.json').read_text())['consumer_argv']\n"
                              '        generated, outer_seconds = execution_command(generated, b, '
                              'admission, i)\n'
                              '        if reference_reuse is not None:\n'
                              '            verify_reference_with_deadline(b, reference_reuse, profile, '
                              'i, reference_reuse_context)\n'
                              "        dut_outer = stage(f'p{i}_dut', generated, outer_seconds, "
                              'accepted=(1, 2), lease_out=lease_root)\n'
                              '        if reference_reuse is not None:\n'
                              '            verify_reference_with_deadline(b, reference_reuse, profile, '
                              'i, reference_reuse_context)\n'
                              "        bundle = profile / 'runtime_bundle.v3.json'\n"
                              '        bundle_doc = json.loads(bundle.read_text())\n'
                              "        runtime_sha = bundle_doc['profiles'][0]['runtime']['sha256']\n"
                              "        diagnostic = dut_evidence.verify(profile / 'dut_result', i, "
                              "sha(manifest), sha(bundle), binary['sha256'], runtime_sha, "
                              "material.pin(out / 'runs' / f'p{i}_dut' / 'RESULT.json'))\n"
                              '        if cloud is not None:\n'
                              '            report = json.loads((profile / '
                              "'dut_result/RESULT.json').read_text())\n"
                              "            need(report.get('executor_identity') == cloud and "
                              "report.get('builder_handoff_sha256') == b['builder_handoff']['sha256'], "
                              "'actual executor report not builder identity')\n"
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
                              "actual['reviewed_budget_sha256'] == admission['reviewed_budget_sha256'], "
                              "'actual consumer full-mode budget identity')\n"
                              '            scope = '
                              "'P0_FIRST_FAULT_READONLY_SAME_FULL_M128_STIMULUS_NOT_NUMERICAL_ACCEPTANCE' "
                              "if admission['mode'] == execution_mode.FIRST_FAULT else "
                              "'STAGE_COVERAGE_DIAGNOSTIC_NOT_FULL_ACCEPTANCE' if admission['mode'] == "
                              'execution_mode.STAGE else '
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
                              "actual.get('stage_budget_sha256') is None, 'actual first-fault document "
                              "identity')\n"
                              '            expected_limits = '
                              "report_effective_limits(actual['original_limits'], b, admission, i)\n"
                              "            need(actual['effective_limits'] == expected_limits, 'actual "
                              "full watchdog limits')\n"
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
                              "runtime['receipt']['sha256'] and ref_doc['runtime_source_pins_sha256'] "
                              "== runtime['sidecar']['sha256'], 'reference matches actual selected "
                              "installed runtime/sidecar')\n"
                              '\n'
                              '        def provider_stage(label, argv):\n'
                              "            return stage(f'p{i}_{label}', argv, lease_out=lease_root)\n"
                              "        initialization = out / 'phases' / f'p{i}_initialize_input.json'\n"
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
                              "'provider_from_frozen.py'), '--initialize-binding', str(initialization), "
                              "'--sha256', sha(initialization)], 120, lease_out=lease_root)\n"
                              "        material.prepare(b['repo'], b['materializer'], profile, i, "
                              "runtime['wrapper'], b['payload'], b['references'][str(i)], "
                              "provider_stage, pins, p0_provider_reuse=b.get('p0_provider_reuse') if i "
                              '== 0 else None)\n'
                              "        stage(f'p{i}_connect', [b['python'], '-B', str(D / "
                              "'connect_owned.py'), '--existing-output', str(profile), '--profile', "
                              'str(i), *identity_args], 120, lease_out=lease_root)\n'
                              '        generated = json.loads((profile / '
                              "'CONSUMER_ARGV.json').read_text())['consumer_argv']\n"
                              '        generated, outer_seconds = execution_command(generated, b, '
                              'admission, i)\n'
                              '        if reference_reuse is not None:\n'
                              '            verify_reference_with_deadline(b, reference_reuse, profile, '
                              'i, reference_reuse_context)\n'
                              "        dut_outer = stage(f'p{i}_dut', generated, outer_seconds, "
                              'accepted=(1, 2), lease_out=lease_root)\n'
                              '        if reference_reuse is not None:\n'
                              '            verify_reference_with_deadline(b, reference_reuse, profile, '
                              'i, reference_reuse_context)\n'
                              "        bundle = profile / 'runtime_bundle.v3.json'\n"
                              '        bundle_doc = json.loads(bundle.read_text())\n'
                              "        runtime_sha = bundle_doc['profiles'][0]['runtime']['sha256']\n"
                              "        diagnostic = dut_evidence.verify(profile / 'dut_result', i, "
                              "sha(manifest), sha(bundle), binary['sha256'], runtime_sha, "
                              "material.pin(out / 'runs' / f'p{i}_dut' / 'RESULT.json'))\n"
                              '        if cloud is not None:\n'
                              '            report = json.loads((profile / '
                              "'dut_result/RESULT.json').read_text())\n"
                              "            need(report.get('executor_identity') == cloud and "
                              "report.get('builder_handoff_sha256') == b['builder_handoff']['sha256'], "
                              "'actual executor report not builder identity')\n"
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
                              "actual['reviewed_budget_sha256'] == admission['reviewed_budget_sha256'], "
                              "'actual consumer full-mode budget identity')\n"
                              "            scope = 'STAGE_COVERAGE_DIAGNOSTIC_NOT_FULL_ACCEPTANCE' if "
                              "admission['mode'] == execution_mode.STAGE else "
                              "'FULL_BLOCK_ACCEPTANCE_REQUIRED_TERMINAL_AND_REFERENCE'\n"
                              "            need(actual['scope'] == scope and "
                              "actual['outer_cleanup_proof_required'] is True, 'actual explicit "
                              "execution scope')\n"
                              "            if admission['mode'] == execution_mode.STAGE:\n"
                              "                need(actual.get('stage_budget_sha256') == "
                              "admission['reviewed_budget_sha256'], 'actual stage coverage budget "
                              "identity')\n"
                              '            expected_limits = '
                              "report_effective_limits(actual['original_limits'], b, admission, i)\n"
                              "            need(actual['effective_limits'] == expected_limits, 'actual "
                              "full watchdog limits')\n"
                              '        dut_records.append(diagnostic)\n'
                              "        save(out / f'PROFILE_{i}_DIAGNOSTIC.json', diagnostic)\n"
                              '        weights(b, i)']]}


# Fixed independently reviewed V2 host deltas; not a new historical baseline.

# Fixed source-reviewed V3 delta, layered before the unchanged V2 inverse.

# Fixed finite-log source delta, layered before unchanged V3/V2/historical proof.

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
                               "scope='SAMPLED_PLANNING_ONLY_PHASE_GATES_UNCHANGED')")],
 'numeric/numeric_tail.py': [('7a4fa6bc7ed201898f0542368513af45ce6c55be8789e059dbe6a7932f559ddb',
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
PRE_AGGREGATE_AST_SHA256 = {'controller/cloud_flow.py': '8b0ded17c7ffbeddd6d098ca6ca90e883606232c9be8e4ad48ff9f2c07a28bed', 'numeric/numeric_tail.py': 'a275e8014536c3bf50b0df6074775ca72ae24f3b90901bbb8aa379a6c5feafe8'}

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
                               16)],
 'numeric/numeric_tail.py': [('dc70475053412b555de36b2bd2a1953f6cae4aeafed6e6c46d99144940d2358b',
                              "if admission.get('budget_version') == 3:\n"
                              "    return dict(full_budget_sha256=admission['reviewed_budget_sha256'], "
                              '**execution_mode.queue_report_fields(admission))',
                              '3543b4693a36a1098850b8bc928887694ed59a6deb7d3dfd0339de01f55a77b6',
                              '',
                              20),
                             ('cfbb7244f31ae7c434e142d614631f083b71e502c351eb18ea3bfe91e27a7ca6',
                              "if admission.get('budget_version') == 3:\n"
                              '    need(type(profile) is int and profile in '
                              "execution_mode.ready_queue_profiles(admission), 'no launch outside admitted "
                              "ready set')",
                              '3543b4693a36a1098850b8bc928887694ed59a6deb7d3dfd0339de01f55a77b6',
                              '',
                              19),
                             ('0b72d4836026850f1c537c698263c11ab75bf0da797d0e0ad0d073f39729cf66',
                              'selected = profile_policy.eligible(b)\n'
                              "if admission.get('budget_version') == 3:\n"
                              "    need(selected == list(range(5)), 'V3 retains all five registered hardware "
                              "profiles')\n"
                              '    return execution_mode.ready_queue_profiles(admission)',
                              'a7860b6e825d10c68405b2ba5cc58c6b4a03652d802536e22f9732e44451ae57',
                              'selected = profile_policy.eligible(b)',
                              18)]}
PRE_V3_AST_SHA256 = {'controller/cloud_flow.py': 'a3464884eb5ee27b7122c74541741e47d6295b9c80af2589b209aebd2941469e', 'numeric/numeric_tail.py': '636bb0b50a1733ae5df7f8a99621244e89f30754eb7226f26d434590cc1efa56'}

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
                               '')],
 'numeric/numeric_tail.py': [('d6a9cb39a22b6577307baa72d3be912f10db9be6c25b414bd50d1ca6b93a8bb5',
                              'PRELAUNCH_SUPERVISOR_SHA = '
                              "'8a7f08366b449f61ea1f18f87ced95f4b4cade4ec1e8359736e2def44c8da82a'",
                              '7c252393a36c825eecb136c3b17873289853ed7d91de99eaeba29eb00f2ac51e',
                              'PRELAUNCH_SUPERVISOR_SHA = '
                              "'c298efb15564b052c7aec7aaf42326de10f392f0e7d28c511fa5def1fcd97791'"),
                             ('7f24cc12c6701bf7b9925ac4f9dd37f47e8a8a60ce89b756ae297a93e34e8d83',
                              "PRELAUNCH_ERRORS = ('ValueError: locked memory gate', 'ValueError: locked "
                              "disk gate', 'ValueError: prelaunch work deadline', 'ValueError: RSS telemetry "
                              "source pin', 'ValueError: exact RSS telemetry policy', 'ValueError: RSS "
                              "telemetry V2 opt-in schema', 'ValueError: finite per-profile RSS raw cap', "
                              "'ValueError: unchanged RSS telemetry 64MiB file cap', 'ValueError: bounded "
                              "RSS observation size', 'ValueError: finite RSS verification "
                              "verification_wall_seconds', 'ValueError: finite RSS verification "
                              "verification_cpu_seconds', 'ValueError: RSS verification CPU within wall "
                              "budget')",
                              '7493cae9633ccb413cf58729ddedf4870181cd81ac6f1a3bac8c446aca2a548b',
                              "PRELAUNCH_ERRORS = ('ValueError: locked memory gate', 'ValueError: locked "
                              "disk gate', 'ValueError: prelaunch work deadline')"),
                             ('0dd230b63916aae7cc1eebf7422130a795faf0fb34a834102dcdfc83d8566aac',
                              'need(sum(execution_mode.profile_reserved_seconds(admission).values()) + '
                              "b['reserved_material_seconds'] + b['reserved_cleanup_seconds'] + "
                              "b['reserved_parent_seconds'] <= (b['job_budget_seconds'] if cloud is not None "
                              "else 21000) - (time.monotonic() - b['job_started_monotonic']), 'whole five "
                              "round exceeds remaining job')",
                              '5362c300de5a534a7de8bcafc7c9f5f9b4308c8631e961f4058d5b1567a86481',
                              "need(sum(admission['profile_seconds'].values()) + "
                              "b['reserved_material_seconds'] + b['reserved_cleanup_seconds'] + "
                              "b['reserved_parent_seconds'] <= (b['job_budget_seconds'] if cloud is not None "
                              "else 21000) - (time.monotonic() - b['job_started_monotonic']), 'whole five "
                              "round exceeds remaining job')"),
                             ('92330720f5ae173ed2f2c49cb16cea06658a1ce798a0b349b26daa8584f6e94a',
                              'return (argv, execution_mode.consumer_phase_seconds(admission, profile))',
                              '4ac614fb54032996340e4400cdcf34169324df961690f1dea9e330614bdb3556',
                              "return (argv, admission['profile_seconds'][str(profile)] + 30)"),
                             ('37c154d6b9c32eba9253955e01ad701d59feb0e405aa62dffdc0e71e6b83bf9a',
                              "dut_profile = int(name[1:-4]) if name.endswith('_dut') else None\n"
                              'telemetry_policy = execution_mode.expected_rss_telemetry_policy(admission, '
                              'dut_profile) if dut_profile is not None else None\n'
                              "telemetry_seconds = telemetry_policy['verification_wall_seconds'] if "
                              'telemetry_policy is not None else 0\n'
                              'admission_seconds = execution_mode.dut_admission_seconds(admission, '
                              "dut_profile, b['reserved_parent_seconds']) if telemetry_policy is not None "
                              'else seconds\n'
                              'body = dict(argv=list(map(str, argv)), pins=pins, '
                              "owned_roots=b['owned_roots'], extra_bytes=b['phase_extra_bytes'], "
                              "seconds=admission_seconds, job_started=b['job_started_monotonic'], "
                              "job_budget_seconds=b['job_budget_seconds'] if cloud is not None else 21000, "
                              "write_file_bytes=128 << 20, tree_cap=b['tree_cap'], environment=e, "
                              'cache_root=str(cache_root), admission_output=str(run_dir / '
                              "'LIVE_ADMISSION.json'))",
                              '3a5a60397c12265515b40e77e449f94a146a7b5ff60c2d565ee02fa5271c504e',
                              'body = dict(argv=list(map(str, argv)), pins=pins, '
                              "owned_roots=b['owned_roots'], extra_bytes=b['phase_extra_bytes'], "
                              "seconds=seconds, job_started=b['job_started_monotonic'], "
                              "job_budget_seconds=b['job_budget_seconds'] if cloud is not None else 21000, "
                              "write_file_bytes=128 << 20, tree_cap=b['tree_cap'], environment=e, "
                              'cache_root=str(cache_root), admission_output=str(run_dir / '
                              "'LIVE_ADMISSION.json'))"),
                             ('fef4e2da70ed309283b9bc203b7a59812f211cb55382da6701bfea9f2eaef96a',
                              'caps = dict(wall_seconds=seconds + 30, cleanup_seconds=30, file_bytes=2 << '
                              '30, tree_bytes=512 << 20, log_bytes=64 << 20, raw_log_bytes=128 << 20, '
                              "max_entries=100000, per_process_as_bytes=b['address_space_bytes'], "
                              'per_process_cpu_seconds=execution_mode.dut_parent_cpu_seconds(admission, '
                              "int(name[1:-4])) if name.endswith('_dut') else seconds + 30, "
                              "rss_bytes=b['rss_bytes'], "
                              'cpu_seconds=execution_mode.dut_aggregate_cpu_seconds(admission, dut_profile, '
                              'seconds) if dut_profile is not None else seconds + 30, '
                              "extra_watch_roots=b['owned_roots'], min_free_disk_bytes=1500000000, "
                              "watch_tree_bytes=b['tree_cap'])\n"
                              'if telemetry_policy is not None:\n'
                              "    caps['rss_telemetry_policy'] = telemetry_policy",
                              '47ec7dae9c1cab079d84dde1d6747ce117930bcbd580812517d3ed40490e68e6',
                              'caps = dict(wall_seconds=seconds + 30, cleanup_seconds=30, file_bytes=2 << '
                              '30, tree_bytes=512 << 20, log_bytes=64 << 20, raw_log_bytes=128 << 20, '
                              "max_entries=100000, per_process_as_bytes=b['address_space_bytes'], "
                              "per_process_cpu_seconds=18000 if name.endswith('_dut') else seconds + 30, "
                              "rss_bytes=b['rss_bytes'], cpu_seconds=seconds + 30, "
                              "extra_watch_roots=b['owned_roots'], min_free_disk_bytes=1500000000, "
                              "watch_tree_bytes=b['tree_cap'])"),
                             ('8bb1717652ea68fa516878a2346ad331cb0afb6f3a75ad845528c4cb0d48d540',
                              "report = json.loads((profile / 'dut_result/RESULT.json').read_text())\n"
                              'expected_log = execution_mode.verify_consumer_admission(admission, '
                              "report.get('execution_admission'), i)\n"
                              "evidence_args = (profile / 'dut_result', i, sha(manifest), sha(bundle), "
                              "binary['sha256'], runtime_sha, material.pin(out / 'runs' / f'p{i}_dut' / "
                              "'RESULT.json'))\n"
                              'if execution_mode.full_v2(admission):\n'
                              '    limits = execution_mode.host_phase_limits(admission, i, '
                              "'evidence_verification')\n"
                              '    with execution_mode.host_verification_budget(**limits):\n'
                              '        execution_mode.verify_supervisor_telemetry(evidence_args[-1], '
                              "admission, i, b['supervisor_dir'], b['pins'])\n"
                              '        diagnostic = dut_evidence.verify(*evidence_args, '
                              'expected_log_policy=expected_log)\n'
                              'else:\n'
                              '    diagnostic = dut_evidence.verify(*evidence_args)',
                              'ed2298310ef79a98c961d0199c880245325dbd72daf10f5c5c2aab9bc70f7a9f',
                              "diagnostic = dut_evidence.verify(profile / 'dut_result', i, sha(manifest), "
                              "sha(bundle), binary['sha256'], runtime_sha, material.pin(out / 'runs' / "
                              "f'p{i}_dut' / 'RESULT.json'))")]}
PRE_V2_AST_SHA256 = {'controller/cloud_flow.py': 'c13b49f746d533261dcb0debf381364bdf9c717ce81cbe876fe4a9c2c559f90d', 'numeric/numeric_tail.py': '4e49e398896618a9749de1b569a1a79d948a7aa943ac641cc2ad088ba8c04ebb'}

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

class Test(unittest.TestCase):
 def tree(self,rel):return ast.parse((D/rel).read_text())
 def test_exact_save_and_reviewed_version_ast(self):
  for rel in EXPECTED:self.check_original_ast(rel,undo_reviewed_v3_delta(self,undo_reviewed_finite_log_delta(self,undo_reviewed_aggregate_cap_delta(self,self.tree(rel),rel),rel),rel))
 def check_original_ast(self,rel,t):
   wanted=EXPECTED[rel]
   t=undo_reviewed_v2_delta(self,t,rel)
   if rel in REVIEWED_STAGE_INVERSE:t=undo_reviewed_stage_delta(self,t,rel)
   if rel=='controller/cloud_flow.py':
    # Undo only the separately reviewed finite prelaunch receipt, not arbitrary flow changes.
    fs=[n for n in ast.walk(t)if isinstance(n,ast.FunctionDef)and n.name=='upfront_disk_admission']
    cs=[n for n in ast.walk(t)if isinstance(n,ast.Call)and isinstance(n.func,ast.Name)and n.func.id=='upfront_disk_admission']
    ds=[n for n in ast.walk(t)if isinstance(n,ast.If)and ast.unparse(n.test)=='evidence_path is not None']
    self.assertEqual((len(fs),len(cs),len(ds)),(1,1,1));f,c,d=fs[0],cs[0],ds[0]
    self.assertIn(d,f.body)
    self.assertEqual(ast.unparse(f.args),'snapshot, evidence_path=None, binding_sha=None')
    self.assertEqual(ast.unparse(c),"upfront_disk_admission(snapshot, P(binding_path).with_name(P(binding_path).name + '.UPFRONT_DISK.json'), binding_sha)")
    self.assertEqual(hashlib.sha256(ast.dump(d,include_attributes=False).encode()).hexdigest(),'c3bb48f0d043a3b02d43bfb69ab5a0a77a81b9938434cde2e836b573d72ba9ad')
    f.args.args=f.args.args[:1];f.args.defaults=[];f.body.remove(d);c.args=c.args[:1]
   class Strip(ast.NodeTransformer):
    count=0
    def visit_Expr(self,n):
     if ast.unparse(n)==wanted:self.count+=1;return None
     return self.generic_visit(n)
   st=Strip();t=st.visit(t)
   with self.subTest(rel=rel):self.assertEqual(st.count,1);self.assertEqual(hashlib.sha256(ast.dump(t).encode()).hexdigest(),BASE_AST[rel])
 def test_actual_stage_statement_order(self):
  for rel,wanted in EXPECTED.items():
   stage=next(n for n in ast.walk(self.tree(rel))if isinstance(n,ast.FunctionDef)and n.name=='stage')
   ix=next(i for i,n in enumerate(stage.body)if isinstance(n,ast.Assign)and isinstance(n.value,ast.Call)and ast.unparse(n.value.func)=='supervisor.execute')
   self.assertEqual(ast.unparse(stage.body[ix+1]),wanted)
   if 'numeric_tail'in rel:self.assertTrue(ast.unparse(stage.body[ix+2]).startswith('require_cleanup('))
   else:self.assertTrue(ast.unparse(stage.body[ix+2]).startswith('history.append('))
 def run_slice(self,rel,r,existing=False):
  stage=next(n for n in ast.walk(self.tree(rel))if isinstance(n,ast.FunctionDef)and n.name=='stage');ix=next(i for i,n in enumerate(stage.body)if isinstance(n,ast.Assign)and isinstance(n.value,ast.Call)and ast.unparse(n.value.func)=='supervisor.execute')
  # Real saved-return statement executes before the original following gate/pin.
  with tempfile.TemporaryDirectory()as td:
   root=pathlib.Path(td);(root/'bindings').mkdir();(root/'phases').mkdir();worker=root/'runs'/'profile0_dut'
   if existing:worker.mkdir(parents=True);(worker/'RESULT.json').write_text('ORIGINAL WORKER RECEIPT')
   def save(p,v):
    with p.open('x')as f:json.dump(v,f)
   def pin(p):return {'bytes':p.stat().st_size}
   def cleanup(receipt,*args):
    if (receipt.get('cleanup_proof')or{}).get('status')!='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP':raise ValueError('original cleanup rejection')
   ns=dict(P=pathlib.Path,supervisor=types.SimpleNamespace(__file__=__file__),job=root,out=root,name='profile0_dut',r=r,run_root=worker,run_dir=worker,save=save,pin=pin,sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest(),history=[],require_cleanup=cleanup)
   block=ast.fix_missing_locations(ast.Module(body=stage.body[ix+1:ix+3],type_ignores=[]))
   try:exec(compile(block,'<actual-stage-save-and-next-check>','exec'),ns)
   except (ValueError,FileNotFoundError):pass
   output=root/('phases'if 'numeric_tail'in rel else'bindings')/'profile0_dut_SUPERVISOR_RETURN.json';self.assertEqual(json.loads(output.read_text()),r)
   if existing:self.assertEqual((worker/'RESULT.json').read_text(),'ORIGINAL WORKER RECEIPT')
   else:self.assertFalse(worker.exists())
 def test_prelaunch_missing_worker_preserves_exact_error(self):
  for rel in EXPECTED:self.run_slice(rel,{'worker_started':False,'native_exit':None,'errors':['ValueError: locked memory gate'],'cleanup_proof':None})
 def test_existing_worker_failure_does_not_overwrite_receipt(self):
  for rel in EXPECTED:self.run_slice(rel,{'worker_started':True,'native_exit':1,'errors':[],'cleanup_proof':{}},True)
 def test_completed_return_remains_separate(self):
  for rel in EXPECTED:self.run_slice(rel,{'worker_started':True,'native_exit':0,'errors':[],'cleanup_proof':{'status':'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'}},True)
class InverseNegativeTests(unittest.TestCase):
 def test_reviewed_delta_mutation_and_duplicate_rejected(self):
  for relative,rows in REVIEWED_STAGE_INVERSE.items():
   root=D.parent if D.name=='numeric'else D
   original=undo_reviewed_v2_delta(self,undo_reviewed_v3_delta(self,undo_reviewed_finite_log_delta(self,undo_reviewed_aggregate_cap_delta(self,ast.parse((root/relative).read_text()),relative),relative),relative),relative)
   # An additional copy cannot silently disappear: unique match count must fail.
   duplicate=undo_reviewed_v2_delta(self,undo_reviewed_v3_delta(self,undo_reviewed_finite_log_delta(self,undo_reviewed_aggregate_cap_delta(self,ast.parse((root/relative).read_text()),relative),relative),relative),relative);duplicate.body.extend(ast.parse(rows[0][1]).body)
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
   original=undo_reviewed_v2_delta(self,undo_reviewed_v3_delta(self,undo_reviewed_finite_log_delta(self,undo_reviewed_aggregate_cap_delta(self,ast.parse((root/relative).read_text()),relative),relative),relative),relative)
   duplicate=undo_reviewed_v2_delta(self,undo_reviewed_v3_delta(self,undo_reviewed_finite_log_delta(self,undo_reviewed_aggregate_cap_delta(self,ast.parse((root/relative).read_text()),relative),relative),relative),relative);duplicate.body.extend(ast.parse(rows[0][1]).body)
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
   raw=(D/relative).read_text();normalized=undo_reviewed_v2_delta(self,undo_reviewed_v3_delta(self,undo_reviewed_finite_log_delta(self,undo_reviewed_aggregate_cap_delta(self,ast.parse(raw),relative),relative),relative),relative)
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
   tree=undo_reviewed_v2_delta(self,undo_reviewed_v3_delta(self,undo_reviewed_finite_log_delta(self,undo_reviewed_aggregate_cap_delta(self,ast.parse((D/relative).read_text()),relative),relative),relative),relative)
   with self.subTest(relative=relative):self.assertEqual(hashlib.sha256(ast.dump(tree,include_attributes=False).encode()).hexdigest(),wanted)
 def test_each_v2_fragment_missing_mutated_or_duplicated_is_rejected(self):
  import copy
  for relative,rows in REVIEWED_V2_INVERSE.items():
   for digest,new_text,old_digest,old_text in rows:
    want=ast.parse(new_text).body;want_dump=[ast.dump(n,include_attributes=False)for n in want]
    for case in ('missing','mutated','duplicate'):
     tree=undo_reviewed_v3_delta(self,undo_reviewed_finite_log_delta(self,undo_reviewed_aggregate_cap_delta(self,ast.parse((D/relative).read_text()),relative),relative),relative);hits=[]
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
   tree=undo_reviewed_v3_delta(self,undo_reviewed_finite_log_delta(self,undo_reviewed_aggregate_cap_delta(self,ast.parse((D/relative).read_text()),relative),relative),relative);tree.body.extend(ast.parse('UNREVIEWED_CALLER_DELTA = 1').body)
   before=ast.dump(tree,include_attributes=False)
   restored=undo_reviewed_v2_delta(self,tree,relative)
   self.assertEqual(ast.dump(tree,include_attributes=False),before,'V2 inverse preserves its caller input')
   self.assertIn('UNREVIEWED_CALLER_DELTA',ast.unparse(restored))
   with self.subTest(relative=relative),self.assertRaises(AssertionError)as caught:Test().check_original_ast(relative,tree)
   self.assertIn(BASE_AST[relative],str(caught.exception),'unrelated delta fails the unchanged historical AST hash')
   self.assertNotIn('one exact reviewed V2 fragment',str(caught.exception))
 def test_exact_v2_supervisor_pin_matches_source(self):
  tree=ast.parse((D/'numeric/numeric_tail.py').read_text())
  pins=[n.value.value for n in tree.body if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='PRELAUNCH_SUPERVISOR_SHA'for t in n.targets)]
  expected='8a7f08366b449f61ea1f18f87ced95f4b4cade4ec1e8359736e2def44c8da82a'
  self.assertEqual(pins,[expected])
  self.assertEqual(hashlib.sha256((D.parent/'ci_frontend_pipeline_r2_20261029/supervise_multiroot.py').read_bytes()).hexdigest(),expected)

 def test_stale_or_unknown_supervisor_pin_is_rejected(self):
  import copy
  original=undo_reviewed_v3_delta(self,undo_reviewed_finite_log_delta(self,undo_reviewed_aggregate_cap_delta(self,ast.parse((D/'numeric/numeric_tail.py').read_text()),'numeric/numeric_tail.py'),'numeric/numeric_tail.py'),'numeric/numeric_tail.py')
  for value in ('8b2308f85fe9f6f8a727716b9df53aab99f111c01eabd0fa35a73d2c65a5f19c','0'*64):
   tree=copy.deepcopy(original)
   pins=[n for n in tree.body if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='PRELAUNCH_SUPERVISOR_SHA'for t in n.targets)]
   self.assertEqual(len(pins),1);pins[0].value=ast.Constant(value=value)
   with self.subTest(pin=value),self.assertRaisesRegex(AssertionError,'one exact reviewed V2 fragment: d6a9cb39a22b6577307baa72d3be912f10db9be6c25b414bd50d1ca6b93a8bb5'):
    undo_reviewed_v2_delta(self,tree,'numeric/numeric_tail.py')


class V3InverseNegativeTests(unittest.TestCase):
 def test_v3_restores_exact_frozen_v2_source_ast(self):
  for relative,wanted in PRE_V3_AST_SHA256.items():
   tree=undo_reviewed_v3_delta(self,undo_reviewed_finite_log_delta(self,undo_reviewed_aggregate_cap_delta(self,ast.parse((D/relative).read_text()),relative),relative),relative)
   with self.subTest(relative=relative):self.assertEqual(hashlib.sha256(ast.dump(tree,include_attributes=False).encode()).hexdigest(),wanted)
 def test_each_v3_fragment_missing_mutated_or_duplicated_is_rejected(self):
  import copy
  for relative,rows in REVIEWED_V3_INVERSE.items():
   self.assertEqual([row[4]for row in rows],sorted((row[4]for row in rows),reverse=True),'reverse reviewed author order')
   for digest,new_text,old_digest,old_text,author_index in rows:
    want=ast.parse(new_text).body;want_dump=[ast.dump(n,include_attributes=False)for n in want]
    for case in ('missing','mutated','duplicate'):
     tree=undo_reviewed_finite_log_delta(self,undo_reviewed_aggregate_cap_delta(self,ast.parse((D/relative).read_text()),relative),relative);hits=[]
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
   tree=undo_reviewed_finite_log_delta(self,undo_reviewed_aggregate_cap_delta(self,ast.parse((D/relative).read_text()),relative),relative);tree.body.extend(ast.parse('UNREVIEWED_V3_CALLER_DELTA = 1').body)
   before=ast.dump(tree,include_attributes=False);restored=undo_reviewed_v3_delta(self,tree,relative)
   self.assertEqual(ast.dump(tree,include_attributes=False),before,'V3 inverse preserves its caller input')
   self.assertIn('UNREVIEWED_V3_CALLER_DELTA',ast.unparse(restored))
   with self.subTest(relative=relative),self.assertRaises(AssertionError)as caught:Test().check_original_ast(relative,restored)
   self.assertIn(BASE_AST[relative],str(caught.exception),'unrelated delta fails original historical AST hash')
   self.assertNotIn('one exact reviewed V3 fragment',str(caught.exception))
   self.assertNotIn('one exact reviewed V2 fragment',str(caught.exception))


class FiniteLogInverseTests(unittest.TestCase):
 def test_finite_log_restores_exact_prior_v3_tail_ast(self):
  restored=undo_reviewed_finite_log_delta(self,undo_reviewed_aggregate_cap_delta(self,ast.parse((D/'numeric/numeric_tail.py').read_text()),'numeric/numeric_tail.py'),'numeric/numeric_tail.py')
  self.assertEqual(hashlib.sha256(ast.dump(restored,include_attributes=False).encode()).hexdigest(),PRE_FINITE_LOG_AST_SHA256)
 def test_each_finite_fragment_missing_mutated_or_duplicated_rejected(self):
  import copy
  for digest,new_text,old_digest,old_text in REVIEWED_FINITE_LOG_INVERSE['numeric/numeric_tail.py']:
   want=ast.parse(new_text).body;want_dump=[ast.dump(n,include_attributes=False)for n in want]
   for case in ('missing','mutated','duplicate'):
    tree=undo_reviewed_aggregate_cap_delta(self,ast.parse((D/'numeric/numeric_tail.py').read_text()),'numeric/numeric_tail.py');hits=[]
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
  tree=undo_reviewed_aggregate_cap_delta(self,ast.parse((D/'numeric/numeric_tail.py').read_text()),'numeric/numeric_tail.py');tree.body.extend(ast.parse('UNREVIEWED_FINITE_LOG_CALLER_DELTA = 1').body)
  before=ast.dump(tree,include_attributes=False);restored=undo_reviewed_finite_log_delta(self,tree,'numeric/numeric_tail.py')
  self.assertEqual(ast.dump(tree,include_attributes=False),before,'finite inverse preserves input')
  self.assertIn('UNREVIEWED_FINITE_LOG_CALLER_DELTA',ast.unparse(restored))
  with self.assertRaises(AssertionError)as caught:Test().check_original_ast('numeric/numeric_tail.py',undo_reviewed_v3_delta(self,restored,'numeric/numeric_tail.py'))
  self.assertIn(BASE_AST['numeric/numeric_tail.py'],str(caught.exception),'original historical hash is rejection reason')
  self.assertNotIn('one exact finite-log fragment',str(caught.exception))
  self.assertNotIn('one exact reviewed V3 fragment',str(caught.exception))


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
   with self.subTest(relative=relative),self.assertRaises(AssertionError)as caught:Test().check_original_ast(relative,undo_reviewed_v3_delta(self,undo_reviewed_finite_log_delta(self,restored,relative),relative))
   self.assertIn(BASE_AST[relative],str(caught.exception),'original historical hash is rejection reason')
   self.assertNotIn('one exact aggregate-cap fragment',str(caught.exception))
   self.assertNotIn('one exact finite-log fragment',str(caught.exception))
   self.assertNotIn('one exact reviewed V3 fragment',str(caught.exception))

if __name__=='__main__':unittest.main()
