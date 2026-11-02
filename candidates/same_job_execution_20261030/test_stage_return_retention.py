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
  for rel,wanted in EXPECTED.items():
   t=self.tree(rel)
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


class FirstFaultInverseNegativeTests(unittest.TestCase):
 def test_exact_first_fault_snippets_changed_or_duplicate_fail(self):
  import copy
  for relative,rows in REVIEWED_FIRST_FAULT_INVERSE.items():
   raw=(D/relative).read_text()
   for digest,new_text,old_text in rows:
    duplicate=ast.parse(raw);duplicate.body.extend(ast.parse(new_text).body)
    with self.subTest(relative=relative,digest=digest,case='duplicate'),self.assertRaises(AssertionError):undo_reviewed_first_fault_delta(self,duplicate,relative)
   changed=ast.parse(raw);hits=0
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

if __name__=='__main__':unittest.main()
