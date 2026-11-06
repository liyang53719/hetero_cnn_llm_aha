"""Unexecuted, renderable original Matrix/ICG build description. No IO or executor."""
import copy
import hashlib
import json
import re

_DATA = {'repository_commit': 'db6fd29aac11a2b70b0c60b3e09106db9256df26',
 'inputs': [{'path': 'candidates/ci_frontend_materialization_r2_20261029/recover_matrix_portable.py',
             'sha256': '059f8d00708018f4aafd51a104d53f459896bd0995f9b356d57e323778cb2ea8',
             'role': 'matrix.provider_reconstructor'},
            {'path': 'candidates/ci_frontend_materialization_r2_20261029/MATRIX_REPO_SOURCE_MAP.json',
             'sha256': 'f13b224355a89e8dcee3e8d90def92f5ec612dc78aedb60ad575984869844d1d',
             'role': 'matrix.provider_source_map'},
            {'path': 'candidates/qwen2_public21_binding/compose.py',
             'sha256': '730994443ca60d750eb13b0561dd3cd0a24ec024bb24be63cf2d1b793071e6c6',
             'role': 'matrix.provider_patch_engine'},
            {'path': 'candidates/qwen2_public21_binding/pinned_source_manifest.json',
             'sha256': '75caad6c8db95ba5470a5d97b6d691f96af17e0bfe58f2ca207693c92097864c',
             'role': 'matrix.provider_patch_manifest'},
            {'path': 'candidates/qwen2_public21_binding/Public21DispatchHarness.scala',
             'sha256': '7d954937af0affaee373374ed9bb258ba492c6178fe8513134059629e52b9a11',
             'role': 'matrix.compose_asset.0'},
            {'path': 'candidates/qwen2_public21_binding/Public21ReductionDispatchControlSpec.scala',
             'sha256': '47e202e7e9124cac8ed16398ca3be3dc7c1e3475216efb5cd176a9a73c6d3d7f',
             'role': 'matrix.compose_asset.1'},
            {'path': 'candidates/qwen2_public21_binding/attention_preflight.patch',
             'sha256': '0959ac40cfe1bee5e9c6cce95c89b21485aa4bfd1c3ed448371a3b4160706000',
             'role': 'matrix.compose_asset.2'},
            {'path': 'candidates/qwen2_public21_binding/current_overlay.patch',
             'sha256': '2774aacc19b2877dc77dae5d145b628aee2e4eb2589c98f917904669b56715ad',
             'role': 'matrix.compose_asset.3'},
            {'path': 'candidates/qwen2_public21_binding/dispatch_abort.patch',
             'sha256': '1db072de18a925d18802ec591136e8cb914e28b982de27c288d66b243da4429e',
             'role': 'matrix.compose_asset.4'},
            {'path': 'candidates/qwen2_public21_binding/evidence/attention_preflight_adapter.py',
             'sha256': 'c40adeae60805d12ec0ba09fcc867cd5262d408829ebee6ef91581af909d2cb0',
             'role': 'matrix.compose_asset.5'},
            {'path': 'candidates/qwen2_public21_binding/evidence/compile_inputs.json',
             'sha256': 'e058f739c15a997d736f510411e6f774cddc12695cc077aa64a541f2b0973b57',
             'role': 'matrix.compose_asset.6'},
            {'path': 'candidates/qwen2_public21_binding/evidence/overlay_manifest.json',
             'sha256': 'e1a77d673be3eaa69508cdfd4650f06a8d2998834e42c35c2a27c3a4e7380e2c',
             'role': 'matrix.compose_asset.7'},
            {'path': 'candidates/qwen2_public21_binding/explicit_resolutions.json',
             'sha256': '0ad8bf705943ece142d4ef54d8f2c172f9716aad2a489203649a96a721cb8b20',
             'role': 'matrix.compose_asset.8'},
            {'path': 'candidates/qwen2_public21_binding/run_control.py',
             'sha256': 'd102e2d567e9f3cc4610bb8fc4e15fedfae3465cfe605b4bc316ffbd9ee27545',
             'role': 'matrix.compose_asset.9'},
            {'path': 'candidates/qwen2_public21_binding/source_audit.py',
             'sha256': 'cec04fbc11bd40fa99fb11be06d4d0260ec1eb020a417043be9e077037da7b31',
             'role': 'matrix.compose_asset.10'},
            {'path': 'candidates/qwen2_public21_binding/test_control_gate.py',
             'sha256': '893028da170939762aa8b278e2a1df4173730652cd78c0781d63174360023d15',
             'role': 'matrix.compose_asset.11'},
            {'path': 'candidates/qwen2_public21_binding/test_source_gate.py',
             'sha256': '7236a82f9f18497f924051cfc088c43b90bd292b0e329573efebcd7d4a9e0508',
             'role': 'matrix.compose_asset.12'},
            {'path': 'rtl/integration/qwen2_matrix_command_endpoint.sv',
             'sha256': '057ce15d3b9fd5153c8873498f9cf1b3f17d7eea64e8928c1208496b3d0bd53a',
             'role': 'matrix.baseline_rtl.0'},
            {'path': 'rtl/matrix/candidates/rev8b_b/bf16_context_fma_pipeline_lane5_rev8b_b_candidate.sv',
             'sha256': 'ad985950e9129c524f685385dac75db9f3bd4ca632e125f7e1b54103271fb418',
             'role': 'matrix.baseline_rtl.1'},
            {'path': 'rtl/matrix/candidates/rev8b_b/bf16_context_front_control5_rev8b_b_candidate.sv',
             'sha256': '0d3bbeee52db023598ebc457420cd2ed8063051363b5c89699730b7f0cbfe6bc',
             'role': 'matrix.baseline_rtl.2'},
            {'path': 'rtl/matrix/candidates/rev8b_b/bf16_context_lane_cluster16_rev8b_b_candidate.sv',
             'sha256': 'be5c10cfe04fe053620883f5bf84646afc990f8c363e1d280ef2dc6b1341148b',
             'role': 'matrix.baseline_rtl.3'},
            {'path': 'rtl/matrix/candidates/rev8b_b/bf16_context_scheduler5_rev8b_b_candidate.sv',
             'sha256': 'a4c37b485f1e7eeed3012372024e8e7207bc33af6ff97bc307a5572aced6890e',
             'role': 'matrix.baseline_rtl.4'},
            {'path': 'rtl/matrix/candidates/rev8b_b/bf16_outer_product_context_array_rev8b_b_candidate.sv',
             'sha256': '541d4a717df08ef65e0ac047c1f83e06b1e3e1bead6553bd97ada24a32a30d59',
             'role': 'matrix.baseline_rtl.5'},
            {'path': 'scripts/idma_source_export_20261017/fixtures/tc_clk.sv',
             'sha256': '93e9747504fa1da6473560341febbfae6c5e917768633a84fc9ef12299293207',
             'role': 'matrix.provider_repo.tc_clk.sv'},
            {'path': 'candidates/qwen2_resident_matrix/production_qk16_rebase/seed_dma_provider_checkpoint/begin_fix/source/rtl/matrix/candidates/rev8b_b/bf16_context_front_control5_rev8b_b_candidate.sv',
             'sha256': '0c9857bf13d6f6fdfd421ea190bf7608ab387746e9e638c55dc763ad8b1984bc',
             'role': 'matrix.provider_repo.bf16_context_front_control5_rev8b_b_candidate.sv'},
            {'path': 'rtl/matrix/bf16_outer_product_array_glue512.sv',
             'sha256': '8d02ba89ffa8b32acbd8bf5677906c71bedd698ac6337df0aa0c06dca1c78fa9',
             'role': 'matrix.provider_repo.bf16_outer_product_array_glue512.sv'},
            {'path': 'rtl/matrix/candidates/rev8b_a/bf16_operand_distribution512_rev8b_a_candidate.sv',
             'sha256': 'e9cdc568bb11f13db3d7653e375e79baa751af4080a9f5bdbc9a3353bbdde471',
             'role': 'matrix.provider_repo.bf16_operand_distribution512_rev8b_a_candidate.sv'},
            {'path': 'rtl/matrix/candidates/rev8b_b/bf16_outer_product_array_control5_rev8b_b_candidate.sv',
             'sha256': 'e1afd499281df0493f1660bbfe8b1a5f6bfeea9e49899b0368372d23d4c790c2',
             'role': 'matrix.provider_repo.bf16_outer_product_array_control5_rev8b_b_candidate.sv'},
            {'path': 'rtl/matrix/candidates/rev8b_b/bf16_context_tag_pipeline5_rev8b_b_candidate.sv',
             'sha256': '0271a1627089578a95144fd0cddd4b9d8d39a6cd27ea327eb48ca399c9bc3ac0',
             'role': 'matrix.provider_repo.bf16_context_tag_pipeline5_rev8b_b_candidate.sv'},
            {'path': 'rtl/matrix/candidates/rev8b_b/bf16_cluster_flags_glue32_rev8b_b_candidate.sv',
             'sha256': '4d39ce9f81ceab8853b1d91f757e8d237d891cc8a875a904599726f5c80d6d3f',
             'role': 'matrix.provider_repo.bf16_cluster_flags_glue32_rev8b_b_candidate.sv'},
            {'path': 'rtl/matrix/candidates/rev8b_b/bf16_front_to_cluster_broadcast32_rev8b_b_candidate.sv',
             'sha256': '991c73df8b263e0a7283e6eb01be85fe283740b450a42a7d1e693114e1bef64b',
             'role': 'matrix.provider_repo.bf16_front_to_cluster_broadcast32_rev8b_b_candidate.sv'},
            {'path': 'candidates/fresh_non_dpi_backend_recovery_20261028/source/PhysicalFmaStageLibrary.scala',
             'sha256': 'bf313312faf48c65d26d250d5b5aa59049b3ec006c99fbc3692557dec7661aaf',
             'role': 'matrix.fma_emitter'},
            {'path': 'candidates/chisel_hybrid_host_20261106/native/matrix_icg/retained_matrix_leaf.cpp',
             'sha256': '041d813eb8677687321aa93cb3705713b5f7f2d3f5f35c1f44941288b26356aa',
             'role': 'matrix_icg.source.retained_matrix_leaf.cpp'},
            {'path': 'candidates/chisel_hybrid_host_20261106/native/matrix_icg/retained_matrix_leaf.h',
             'sha256': '63301a207240a0eac68c998dd2d4c6fb8eaf5f56efdf3f7b890449be329e398a',
             'role': 'matrix_icg.source.retained_matrix_leaf.h'},
            {'path': 'candidates/chisel_hybrid_host_20261106/native/matrix_icg/retained_icg_leaf.cpp',
             'sha256': '707f298f8c2111d38373a6e521bed2432ffcc6a5a27959dec2a176727f6a7412',
             'role': 'matrix_icg.source.retained_icg_leaf.cpp'},
            {'path': 'candidates/chisel_hybrid_host_20261106/native/matrix_icg/retained_icg_leaf.h',
             'sha256': 'f0f29f37cd5b95a0ded211ba79bf41aa0a97a917164d773051e221f5ab360adc',
             'role': 'matrix_icg.source.retained_icg_leaf.h'},
            {'path': 'candidates/chisel_hybrid_host_20261106/native/matrix_icg/trace_io.h',
             'sha256': '604fa782be18424b421dc262319d5486636ed91d66947a035e9639c691cf3e12',
             'role': 'matrix_icg.source.trace_io.h'},
            {'path': 'candidates/chisel_hybrid_host_20261106/native/matrix_icg/matrix_direct_trace.cpp',
             'sha256': '58d9be8211ebb6af31ce551b2689e63899763a48e319cf581aa16f301cafbea1',
             'role': 'matrix_icg.source.matrix_direct_trace.cpp'},
            {'path': 'candidates/chisel_hybrid_host_20261106/native/matrix_icg/matrix_cabi_trace.cpp',
             'sha256': '2aeea8381db8b9ca2311c7f833927739344033ae1e137bb02e714aa53796a1e0',
             'role': 'matrix_icg.source.matrix_cabi_trace.cpp'},
            {'path': 'candidates/chisel_hybrid_host_20261106/native/matrix_icg/icg_direct_trace.cpp',
             'sha256': '8b7464187d011fcde5c1ddb7fe96994e20abe9284849c9340a16b75985d80ceb',
             'role': 'matrix_icg.source.icg_direct_trace.cpp'},
            {'path': 'candidates/chisel_hybrid_host_20261106/native/matrix_icg/icg_cabi_trace.cpp',
             'sha256': '0031ae235749b299dc39e6f42b44ebc5f34e134c7d140a09699ce70267b7e92b',
             'role': 'matrix_icg.source.icg_cabi_trace.cpp'},
            {'path': 'candidates/chisel_hybrid_host_20261106/native/matrix_icg/passive_native_mapping.h',
             'sha256': '4bb5ae7975b8bcb908b879a026def11b0f2b44d88c8c9ed09d7360f87abc9d37',
             'role': 'matrix_icg.source.passive_native_mapping.h'}],
 'provider_files': {'tc_clk.sv': '93e9747504fa1da6473560341febbfae6c5e917768633a84fc9ef12299293207',
                    'qwen2_matrix_command_endpoint.sv': 'ea16cf4221b52412a5ba1f3f23efeb198077790e271a6f6a1a51a43e82fad4ac',
                    'bf16_context_scheduler5_rev8b_b_candidate.sv': '33cf6bbd37ef1d2b537e948a29cf642f51ce4d8b34fa2483294c4f604b925ac0',
                    'bf16_context_fma_pipeline_lane5_rev8b_b_candidate.sv': '6d276382a0e3e1b7145b381c700e895806e6f382bcb044d53c2279c98757d19c',
                    'bf16_outer_product_context_array_rev8b_b_candidate.sv': '41d801167ff90547cde5d2a1784f964920873d5f3ba0d1c9654b79eebc2c6a27',
                    'bf16_context_front_control5_rev8b_b_candidate.sv': '0c9857bf13d6f6fdfd421ea190bf7608ab387746e9e638c55dc763ad8b1984bc',
                    'bf16_context_lane_cluster16_rev8b_b_candidate.sv': 'c7fd146302112613515e6fa86af152496cb8d753ef9a425eb0cdbe0252ef073e',
                    'bf16_outer_product_array_glue512.sv': '8d02ba89ffa8b32acbd8bf5677906c71bedd698ac6337df0aa0c06dca1c78fa9',
                    'bf16_operand_distribution512_rev8b_a_candidate.sv': 'e9cdc568bb11f13db3d7653e375e79baa751af4080a9f5bdbc9a3353bbdde471',
                    'bf16_outer_product_array_control5_rev8b_b_candidate.sv': 'e1afd499281df0493f1660bbfe8b1a5f6bfeea9e49899b0368372d23d4c790c2',
                    'bf16_context_tag_pipeline5_rev8b_b_candidate.sv': '0271a1627089578a95144fd0cddd4b9d8d39a6cd27ea327eb48ca399c9bc3ac0',
                    'bf16_cluster_flags_glue32_rev8b_b_candidate.sv': '4d39ce9f81ceab8853b1d91f757e8d237d891cc8a875a904599726f5c80d6d3f',
                    'bf16_front_to_cluster_broadcast32_rev8b_b_candidate.sv': '991c73df8b263e0a7283e6eb01be85fe283740b450a42a7d1e693114e1bef64b'},
 'matrix_filelist': ['qwen2_matrix_command_endpoint.sv',
                     'bf16_context_scheduler5_rev8b_b_candidate.sv',
                     'bf16_context_fma_pipeline_lane5_rev8b_b_candidate.sv',
                     'bf16_outer_product_context_array_rev8b_b_candidate.sv',
                     'bf16_context_front_control5_rev8b_b_candidate.sv',
                     'bf16_context_lane_cluster16_rev8b_b_candidate.sv',
                     'bf16_outer_product_array_glue512.sv',
                     'bf16_operand_distribution512_rev8b_a_candidate.sv',
                     'bf16_outer_product_array_control5_rev8b_b_candidate.sv',
                     'bf16_context_tag_pipeline5_rev8b_b_candidate.sv',
                     'bf16_cluster_flags_glue32_rev8b_b_candidate.sv',
                     'bf16_front_to_cluster_broadcast32_rev8b_b_candidate.sv'],
 'icg_filelist': ['tc_clk.sv'],
 'fma': {'bytes': 194835,
         'sha256': 'cfd73d73400853e9be9adbfc8ca0abeba7e8a88668d09dcc7dc3a46f18b21d53',
         'modules': ['MulAddRecFNToRaw_preMul_e8_s24',
                     'HeteroBF16FmaPre',
                     'HeteroBF16FmaMul',
                     'MulAddRecFNToRaw_postMul_e8_s24',
                     'HeteroBF16FmaPost',
                     'RoundAnyRawFNToRecFN_ie8_is26_oe8_os24',
                     'RoundRawFNToRecFN_e8_s24',
                     'HeteroBF16FmaRound',
                     'PhysicalFmaStageLibrary']},
 'unit_names': {'matrix': ['Vqwen2_matrix_command_endpoint.cpp',
                           'Vqwen2_matrix_command_endpoint___024root__DepSet_he959708b__0.cpp',
                           'Vqwen2_matrix_command_endpoint___024root__DepSet_he959708b__1.cpp',
                           'Vqwen2_matrix_command_endpoint___024root__DepSet_he959708b__2.cpp',
                           'Vqwen2_matrix_command_endpoint___024root__DepSet_he63927f2__0.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_lane_cluster16_rev8b_b_candidate__pi4__DepSet_h290cff80__0.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__0.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__1.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__2.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__3.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__4.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__5.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__6.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__7.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__8.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__9.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__10.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__11.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__12.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__13.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__14.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__15.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__16.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__17.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__18.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__19.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__20.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__21.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__22.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__23.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__24.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__25.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__26.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__27.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__28.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__29.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__30.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__31.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__32.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__33.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__34.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__35.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__36.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__37.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__38.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__39.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__40.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__41.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__42.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__43.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__44.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__45.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__46.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__47.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__48.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__49.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__50.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__51.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__52.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__53.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__54.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__55.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__56.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__57.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__58.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__59.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__60.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__61.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__62.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__63.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__64.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__65.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__66.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__67.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__68.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__69.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__70.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__71.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__72.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__73.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__74.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__75.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__76.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__77.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__78.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__79.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__80.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__81.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__82.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__83.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__84.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__85.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__86.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__87.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__88.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__89.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__90.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__91.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__92.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__93.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__94.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__95.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__96.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__97.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__98.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__99.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__100.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__101.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__102.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__103.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__104.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__105.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__106.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__107.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__108.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__109.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__110.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__111.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__112.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__113.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__114.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__115.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__116.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__117.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__118.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__119.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__120.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__121.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__122.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__123.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__124.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__125.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__126.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__127.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__128.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__129.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__130.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__131.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__132.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__133.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__134.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__135.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__136.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__137.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__138.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__139.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__140.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__141.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__142.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__143.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__144.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__145.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__146.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__147.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__148.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__149.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__150.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__151.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__152.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__153.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__154.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__155.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__156.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__157.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__158.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__159.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__160.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__161.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__162.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__163.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__164.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__165.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__166.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__167.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__168.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__169.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__170.cpp',
                           'Vqwen2_matrix_command_endpoint___024root__Slow.cpp',
                           'Vqwen2_matrix_command_endpoint___024root__DepSet_he959708b__0__Slow.cpp',
                           'Vqwen2_matrix_command_endpoint___024root__DepSet_he63927f2__0__Slow.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_lane_cluster16_rev8b_b_candidate__pi4__Slow.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_lane_cluster16_rev8b_b_candidate__pi4__DepSet_hf1e29c44__0__Slow.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__Slow.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__0__Slow.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__1__Slow.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__2__Slow.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__3__Slow.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__4__Slow.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__5__Slow.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__6__Slow.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_h85d03096__7__Slow.cpp',
                           'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6__DepSet_hb9c1e805__0__Slow.cpp',
                           'Vqwen2_matrix_command_endpoint__Syms.cpp'],
                'icg': ['Vtc_clk_gating.cpp',
                        'Vtc_clk_gating___024root__DepSet_hc43f5906__0.cpp',
                        'Vtc_clk_gating___024root__DepSet_h6795f921__0.cpp',
                        'Vtc_clk_gating___024root__Slow.cpp',
                        'Vtc_clk_gating___024root__DepSet_hc43f5906__0__Slow.cpp',
                        'Vtc_clk_gating___024root__DepSet_h6795f921__0__Slow.cpp',
                        'Vtc_clk_gating__Syms.cpp']},
 'generated_headers': {'matrix': {'Vqwen2_matrix_command_endpoint.h': 'bcf14e97f985f73d3e1d51257323e0570b6e8c957f367dabef7030ec33e08ecf',
                                  'Vqwen2_matrix_command_endpoint__Syms.h': 'b05ba6ee07e0feaeb0850ba6f4d7aa1d2c44bc06b8f06c4488277abdefdecda0',
                                  'Vqwen2_matrix_command_endpoint___024root.h': '8c4e845531234dda458b73ef70b43fb810c4ff4584e74127bb7fc166b732e625',
                                  'Vqwen2_matrix_command_endpoint__pch.h': 'e312c1930da6c4afb491df62aed8dd791a79b0cbdc5e8c5bc9269d8dc29a00d1',
                                  'Vqwen2_matrix_command_endpoint_bf16_context_fma_pipeline_lane5_rev8b_b_candidate__pi6.h': '8b96bed670523e8d133c49c72ff3733ad8f213f39a87744cf15909c5866015c4',
                                  'Vqwen2_matrix_command_endpoint_bf16_context_lane_cluster16_rev8b_b_candidate__pi4.h': 'e2a733035e658d66dc0dea99c91aa5bd0200624ad52f27c2be1a03a9e13940e7'},
                       'icg': {'Vtc_clk_gating.h': '972f85921dc524724ac58871cd2c7105a77f5978ca66a45c746533d6a83f13ed',
                               'Vtc_clk_gating__Syms.h': '20ad7590b8590e5a5a5f50d337e8e9f58804ef55bc649eda6192cdfa892b91e1',
                               'Vtc_clk_gating___024root.h': '69555d5a573c90c1af38f621e7afe8751c9db309e34599cb34b4d1b7207e1ff7',
                               'Vtc_clk_gating__pch.h': '91fef5df0038129c413d3e5e3178e2ad7569212f59151691d97b8e8b49e70c2e'}},
 'generated_compile_flags': ['-O1',
                             '-I.',
                             '-MMD',
                             '-I{artifact:verilator_root}/include',
                             '-I{artifact:verilator_root}/include/vltstd',
                             '-DVM_COVERAGE=0',
                             '-DVM_SC=0',
                             '-DVM_TIMING=0',
                             '-DVM_TRACE=0',
                             '-DVM_TRACE_FST=0',
                             '-DVM_TRACE_VCD=0',
                             '-faligned-new',
                             '-fcf-protection=none',
                             '-Wno-bool-operation',
                             '-Wno-shadow',
                             '-Wno-sign-compare',
                             '-Wno-tautological-compare',
                             '-Wno-uninitialized',
                             '-Wno-unused-but-set-parameter',
                             '-Wno-unused-but-set-variable',
                             '-Wno-unused-parameter',
                             '-Wno-unused-variable',
                             '-fPIC']}


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _stage(name, cwd, argv, inputs, outputs, *preconditions):
    return dict(id='matrix_icg.' + name, cwd=cwd, argv=argv, inputs=inputs,
                outputs=outputs, preconditions=list(preconditions), unexecuted=True)


def _canonical_description():
    """Construct the exact source-reviewed contract, without IO or validation recursion."""
    d = copy.deepcopy(_DATA)
    d['inputs'] += [
        {'path':'candidates/chisel_hybrid_host_20261106/SOURCES.json',
         'sha256':'18cf729970d190eae2409b6128ceb8563f3ab043bdebb599920f5881e43a22be',
         'role':'matrix_icg.scala_source_manifest'},
        {'path':'candidates/chisel_hybrid_host_20261106/MAVEN_INPUTS.json',
         'sha256':'b7c3d85d7ce5f8ecf82dc77dd154e9f9e5f830bc0a63e3437d0f4ac15250fb3d',
         'role':'matrix_icg.maven_manifest'},
        {'path':'candidates/chisel_hybrid_host_20261106/compile_only.py',
         'sha256':'eeb7ba0eda44b3c4a76003ac34c1e1ba303231ec5a7eec7fffd95abce2fcb8f7',
         'role':'matrix_icg.scala_compiler_source'}]
    repo = '{repo}/candidates/chisel_hybrid_host_20261106/native/matrix_icg'
    build = '{build}/matrix_icg'
    inc = '{artifact:verilator_root}/include'
    common = ['-std=c++17', '-O1', '-fPIC', '-pthread']
    runtime = [inc + '/verilated.cpp', inc + '/verilated_threads.cpp']
    java = ['{tool:java}', '-XX:-UsePerfData', '-XX:ActiveProcessorCount=1',
            '-XX:ReservedCodeCacheSize=128m', '-XX:-HeapDumpOnOutOfMemoryError',
            '-XX:ErrorFile=/dev/null', '-Xss4m', '-Xmx2g']
    cp = '{artifact:scala_dependency_classpath}:{artifact:original162_class_root}'
    stages = [_stage('providers', '{build}', [
        '{tool:python}', '-B', '{repo}/candidates/ci_frontend_materialization_r2_20261029/recover_matrix_portable.py',
        '--repo', '{repo}', '--output', build + '/providers'],
        ['matrix.provider_reconstructor', 'matrix.provider_source_map', 'matrix.provider_patch_engine',
         'matrix.provider_patch_manifest', 'matrix.compose_assets', 'matrix.original_rtl'],
        ['matrix_icg.providers'], 'Fresh output; verify every listed source/asset byte before import.',
        'Reconstructor hashes all 13 emitted provider bytes; no generated RTL is distributed.'),
        _stage('fma_compile', build + '/fma/classes', java + ['-cp', '{artifact:scala_dependency_classpath}',
        'scala.tools.nsc.Main', '-classpath', cp, '-Xplugin:{artifact:chisel_plugin}',
        '-Xplugin-require:chiselplugin', '-language:reflectiveCalls', '-d', '.',
        '{repo}/candidates/fresh_non_dpi_backend_recovery_20261028/source/PhysicalFmaStageLibrary.scala'],
        ['matrix.fma_emitter', 'matrix_icg.scala_dependencies', 'matrix_icg.original162'],
        ['matrix_icg.fma_classes'], 'Fresh exclusive class root; previously compiled original162 is an external prerequisite.'),
        _stage('fma_emit', build + '/fma', java + ['-cp', build + '/fma/classes:' + cp,
        'chiseltest.simulator.EmitPhysicalFmaStageLibrary', 'generated'],
        ['matrix_icg.fma_classes', 'matrix_icg.scala_dependencies', 'matrix_icg.original162'],
        ['matrix_icg.fma_sv'], 'All nine modules and zero arithmetic ExtModules; never substitute partial four-module output.',
        'Compare complete output bytes against recorded FMA hash; a mismatch requires review, not rebaselining.')]
    for kind in ('matrix', 'icg'):
        top = 'qwen2_matrix_command_endpoint' if kind == 'matrix' else 'tc_clk_gating'
        prefix = 'V' + top
        gen = build + '/' + kind + '/generated'
        obj = build + '/' + kind + '/objects'
        filelist = build + '/' + kind + '/sources.f'
        argv = ['{tool:verilator_bin}', '--cc', '--Mdir', gen, '--top-module', top,
                '--prefix', prefix, "-GENABLE_ACCUMULATOR_SEED=1'b1" if kind == 'matrix' else "-GIS_FUNCTIONAL=1'b1"]
        if kind == 'matrix':
            argv += ['--output-split', '10000', '--output-split-cfuncs', '10000']
        argv += ['-CFLAGS', '-fPIC', '-f', filelist]
        if kind == 'matrix':
            argv += [build + '/fma/generated/PhysicalFmaStageLibrary.sv', '-Wno-fatal']
        stages.append(_stage(kind + '_generate', build, argv,
            ['matrix_icg.providers', 'matrix_icg.' + kind + '_source_list'] + (['matrix_icg.fma_sv'] if kind == 'matrix' else []),
            ['matrix_icg.' + kind + '_generated'],
            'Direct pinned executable, never the dirname/Perl wrapper; VERILATOR_ROOT explicitly bound.',
            'Stack soft limit must match the recorded unlimited wrapper setting under a separately admitted finite owner.',
            'Fresh output; exact top/parameter/full port ABI and complete generated unit/header census required.',
            'Recorded Matrix 131 warnings must be classified, not ignored because -Wno-fatal is present.' if kind == 'matrix' else 'No generation warnings accepted.'))
        for i, unit in enumerate(d['unit_names'][kind]):
            output = obj + '/' + unit[:-4] + '.o'
            # The historical generated-unit compile did NOT add -std=c++17.
            stages.append(_stage(kind + '_compile_' + str(i), gen,
                ['{tool:cxx}'] + d['generated_compile_flags'] + ['-c', '-o', output, gen + '/' + unit],
                ['matrix_icg.' + kind + '_generated', 'matrix_icg.verilator_headers'],
                ['matrix_icg.' + kind + '_object_' + str(i)],
                'One compiler at a time; no PCH/ccache; exact .d dependency closure must be verified.'))
        archive = obj + '/' + prefix + '__portable.a'
        stages.append(_stage(kind + '_archive', obj,
            ['{tool:ar}', '-rcs', archive] + [obj + '/' + x[:-4] + '.o' for x in d['unit_names'][kind]],
            ['matrix_icg.' + kind + '_object_' + str(i) for i in range(len(d['unit_names'][kind]))],
            ['matrix_icg.' + kind + '_archive'],
            'Archive absent; exact ordered members/content and symbol index must be checked.',
            'GNU ar may hold a second full archive internally: budget both copies.'))
        includes = ['-I' + gen, '-I' + inc, '-I' + inc + '/vltstd', '-I' + repo]
        libname = 'retained_matrix' if kind == 'matrix' else 'retained_icg_requalified'
        stages.append(_stage(kind + '_bridge', build, ['{tool:cxx}'] + common + includes + [
            '-shared', '-Wl,-z,defs', repo + '/retained_' + kind + '_leaf.cpp', archive] + runtime + [
            '-o', build + '/lib/lib' + libname + '.so'],
            ['matrix_icg.source.retained_' + kind + '_leaf.cpp', 'matrix_icg.source.retained_' + kind + '_leaf.h',
             'matrix_icg.' + kind + '_archive', 'matrix_icg.verilator_runtime'],
            ['matrix_icg.' + kind + '_library'], 'Fresh output; exact ABI exports/ELF dependencies/relocations checked before any load.'))
        stages.append(_stage(kind + '_direct_runner', build, ['{tool:cxx}'] + common + includes + [
            repo + '/' + kind + '_direct_trace.cpp', archive] + runtime + [
            '-o', build + '/bin/' + kind + '_direct_trace_observed'],
            ['matrix_icg.source.' + kind + '_direct_trace.cpp', 'matrix_icg.source.trace_io.h',
             'matrix_icg.source.passive_native_mapping.h', 'matrix_icg.' + kind + '_archive', 'matrix_icg.verilator_runtime'],
            ['matrix_icg.' + kind + '_direct_binary'], 'Compile/link only; do not execute the runner.'))
        stages.append(_stage(kind + '_cabi_runner', build, ['{tool:cxx}'] + common + includes + [
            repo + '/' + kind + '_cabi_trace.cpp', '-L' + build + '/lib', '-l' + libname,
            '-Wl,-rpath,$ORIGIN/../lib', '-o', build + '/bin/' + kind + '_cabi_trace_observed'],
            ['matrix_icg.source.' + kind + '_cabi_trace.cpp', 'matrix_icg.source.retained_' + kind + '_leaf.h',
             'matrix_icg.source.trace_io.h', 'matrix_icg.source.passive_native_mapping.h', 'matrix_icg.' + kind + '_library'],
            ['matrix_icg.' + kind + '_cabi_binary'],
            'Proposed relocation only: literal $ORIGIN must not be expanded by a shell; fresh ELF/map qualification required.'))
    result = dict(schema='PORTABLE_NATIVE_RECIPE_FRAGMENT_V1', component='matrix_icg',
        status='UNRUN_PORTABLE_BUILD_RECIPE', execution_authority=False, unexecuted=True,
        repository_commit=d['repository_commit'], inputs=d['inputs'], stages=stages,
        placeholders={'repo':'Exact checked source checkout', 'build':'Fresh ignored build root; disjoint from sources',
          'tool:python':'Bound Python 3 interpreter for source composition', 'tool:java':'JDK 21 executable',
          'tool:verilator_bin':'Real Verilator 5.032 executable, not wrapper', 'tool:cxx':'GNU g++ 14 x86_64 Linux',
          'tool:ar':'GNU ar with SysV archive/index support',
          'artifact:verilator_root':'Matching Verilator 5.032 share/verilator root',
          'artifact:scala_dependency_classpath':'106 ordered role=classpath Maven rows from published MAVEN_INPUTS.json, colon-joined',
          'artifact:original162_class_root':'Fresh verified original162 output from existing Scala-only compilation',
          'artifact:chisel_plugin':'Exact chisel-plugin_2.13.16/6.7.0 jar'},
        tools=[{'id':'verilator_bin','version':'5.032 (recorded Debian 5.032-1+b2)',
          'prior_binary_sha256':'619464a17a8c212219abceeeee23f529b72801ef594814ae32f4b9747fd38703',
          'required_components':['matching include tree','verilated.cpp','verilated_threads.cpp','loader/ELF dependency closure']},
          {'id':'cxx','version':'GNU g++ 14; minor version must be independently qualified',
          'prior_binary_sha256':'6b3696e4dcb85e1c949c732a02befa50e3983ecf94ce7e8e58d9d503b954b79d',
          'required_components':['cc1plus','internal specs','system C/C++ includes','assembler','linker','CRT objects','libc/libm linker scripts','loader','libstdc++/libgcc/libc/libm']},
          {'id':'ar','version':'GNU ar; exact version/dispatch closure must be qualified',
          'prior_binary_sha256':'f8fe09d485b40b1d47c534c96f5cbaaa9148e247aa0494c087104421f48ac5eb',
          'required_components':['libbfd dependencies','loader']},
          {'id':'java','version':'JDK 21','required_components':['Scala 2.13.16 compiler/library/reflect','Chisel 6.7.0 and matching plugin','firrtl2 6.0.0','chiseltest 6.0.0','full original162 HardFloat/gemmini classes']},
          {'id':'python','version':'Python 3; future owner must bind exact executable/stdlib','required_components':['source recovery and exact patching only']}],
        generated_contract={'provider_files':d['provider_files'], 'provider_bytes':43047,
          'filelist_order':{'matrix':d['matrix_filelist'],'icg':d['icg_filelist']},
          'filelist_format':'One absolute resolved provider path per line, final newline; path list is new build-local data, not committed RTL.',
          'fma':d['fma'], 'unit_names':d['unit_names'], 'headers':d['generated_headers'],
          'generated_compile_flags':d['generated_compile_flags'],
          'ABI':{'matrix_top':'qwen2_matrix_command_endpoint','matrix_seed':True,'icg_top':'tc_clk_gating','icg_functional':True,
                 'matrix_input_words':63,'matrix_output_words':533,'service_instances':8,'MACs_per_instance':512,'total_MACs':4096,
                 'boundary':'One reusable native leaf model per type; the original Chisel service instantiates eight independent native handles. This recipe does not elaborate or qualify that service.'}},
        prior_outputs=[{'role':'matrix_library','bytes':7951136,'sha256':'64b773f5687e448c692000bb0f232a9349b18f2e4a8ad98499f2645f063a7c06'},
          {'role':'icg_library','bytes':259824,'sha256':'ee4598046816cb86cbb7a537d3106dee8330280ac3be244892e6de97055a2802'},
          {'role':'matrix_direct_binary','bytes':7670392,'sha256':'230e0a81b66181a0756f08bc30ed600ae84663877ea9bd6d1823281af246ad5f'},
          {'role':'matrix_cabi_binary','bytes':43968,'sha256':'42c7b7a3e71e4113571996e31d0b113e1273dad1dcce7816e668b173843db9b2'},
          {'role':'icg_direct_binary','bytes':233720,'sha256':'cd271ea28e6d1a93259063a59da3b0d985d648a2ffce0e34efe937c1ae0f5b12'},
          {'role':'icg_cabi_binary','bytes':43664,'sha256':'b9ae6e3ec388eb8864259b4715ef7ab7ccba9c1d1c20c264c7bef7fc6c7dd530'}],
        portability_deltas=[
          'All prior absolute workspace/tool/output paths are explicit caller-bound tokens. Source bytes, top names, seed/ICG parameters, partition flags, arithmetic and interfaces are not changed.',
          'Matrix objects previously used object-only make with no-PCH rules. Proposed direct per-unit compiler commands retain the exact recorded compiler option vector, but this new dispatch has not run.',
          'ICG already used seven separate generated units, never the old aggregate-TU archive helper route.',
          'CABI previously embedded an absolute build-library directory in rpath. New bin/../lib layout proposes literal $ORIGIN/../lib; this is not byte-identical linkage or prior loader acceptance.',
          'Provider bytes are exact-testable. Complete FMA bytes and generated headers carry comparison targets; any difference is a blocker for review. Relocated generated make/dependency/stat metadata will differ and needs enumerated validation.',
          'Native ELF binaries may differ with paths/toolchain/linker/build IDs; prior hashes are historical identities, not a portable output certificate. ABI, loaded maps and finite runtime must be requalified separately.',
          'Passive runner observations depend on Linux /proc and POSIX APIs; this is source-relative x86_64 Linux reconstruction, not cross-OS portability.'],
        unresolved_prerequisites=[
          'No portable build stage has executed. A separately reviewed finite owner, complete shared resource ledger, cleanup and output admission are required.',
          'No verified new tool/sysroot/ELF/loader/environment closure is supplied; historical binary hashes alone are insufficient.',
          'Existing Scala compiler must produce and verify original162 classes, exact ordered Maven classpath and plugin; the separate FMA producer then needs fresh class-origin/complete output proof.',
          'Provider source transitive assets, baseline bytes and every source file must be verified in the actual checkout before helper import. No implicit git fallback or downloaded RTL is allowed.',
          'Fresh output directories and two exact ordered source-list files need a reviewed no-clobber preparation owner; describe() creates neither.',
          'Generated exact unit/header set and full ABI checks, all .d dependency paths, archive member/index checks and ELF checks need a future owning validator.',
          'Portable rpath and runtime maps/locale dependencies are unqualified; build-only output never authorizes model loading or numerical/Host acceptance.'])
    result['artifacts'] = {key.split(':', 1)[1]: {'description': value, 'verified': False}
                           for key, value in result['placeholders'].items() if key.startswith('artifact:')}
    result['artifacts'].update({
        'matrix.compose_assets': {
            'description':'Exact aggregate of every transitive asset hashed by compose.load_inputs; no source replacement.',
            'source_roles':[r['role'] for r in d['inputs'] if r['role'].startswith('matrix.compose_asset.')],
            'verified':False},
        'matrix.original_rtl': {
            'description':'Exact source map baseline plus direct provider paths; strict patch reconstruction, never fuzzy application.',
            'source_roles':[r['role'] for r in d['inputs'] if r['role'].startswith(('matrix.baseline_rtl.','matrix.provider_repo.'))],
            'verified':False},
        'matrix_icg.scala_dependencies': {
            'description':'All 106 ordered classpath roles and one plugin role from the exact Maven manifest; actual new jars/class origin unverified.',
            'source_roles':['matrix_icg.maven_manifest'],
            'artifact_refs':['scala_dependency_classpath','chisel_plugin'], 'verified':False},
        'matrix_icg.original162': {
            'description':'All 162 original source rows in the exact published Scala source manifest, including original HardFloat and gemmini providers; fresh 896-class root must be independently verified.',
            'source_roles':['matrix_icg.scala_source_manifest','matrix_icg.scala_compiler_source','matrix_icg.maven_manifest'],
            'artifact_refs':['original162_class_root'], 'verified':False},
        'matrix_icg.verilator_headers': {
            'description':'Matching Verilator 5.032 complete include/vltstd and transitive generated/system include closure; three hashes alone are not a full tool closure.',
            'artifact_refs':['verilator_root'], 'verified':False},
        'matrix_icg.verilator_runtime': {
            'description':'Exact prior runtime sources plus their full future transitive header/tool closure.',
            'artifact_refs':['verilator_root'], 'verified':False,
            'recorded_runtime_sha256': {
                'include/verilated.cpp':'ccb2ed63ef9e66fe27f35da19985326e237eaa65bcec4b5f6eb8d491e5a1bc08',
                'include/verilated.h':'820e0283832d923d2445a916ac247e24d743ece653c5bd8425a3adb00d02d86b',
                'include/verilated_threads.cpp':'9350dd53366540e16f2516e1391ff6b50520da189206d5d76bcb0fefc9fe761a'}},
        'matrix_icg.matrix_source_list': {
            'description':'Uncreated build-local sources.f: exactly ordered Matrix provider paths and final newline; no glob expansion.',
            'requires_output_roles':['matrix_icg.providers'], 'verified':False},
        'matrix_icg.icg_source_list': {
            'description':'Uncreated build-local sources.f: only the exact tc_clk.sv provider path and final newline.',
            'requires_output_roles':['matrix_icg.providers'], 'verified':False}})
    result['aggregate_roles'] = {}
    result['prerequisite_roles'] = {}
    for role, descriptor in result['artifacts'].items():
        members = descriptor.get('source_roles', []) + descriptor.get('artifact_refs', [])
        if members:
            result['aggregate_roles'][role] = members
        else:
            result['prerequisite_roles'][role] = {
                'requires':descriptor.get('requires_output_roles', []),
                'description':descriptor['description'] + '; explicitly unmaterialized or not newly qualified.'}
    for tool in result['tools']:
        if tool['id'] in ('java', 'python'):
            tool['identity_status'] = 'UNRESOLVED'
            tool['identity_prerequisite'] = (
                'Bind exact JDK 21 executable, runtime modules, dynamic loader/ELF and ordered Maven/compiler/plugin closure before any producer compilation or emission.'
                if tool['id'] == 'java' else
                'Bind exact Python executable, stdlib/import dispatch, dynamic loader/ELF and source-reconstruction helper closure before invoking the preserved helper.')
    return result


def describe():
    """Return a fresh JSON-safe command description; never read, write or run anything."""
    result = _canonical_description()
    validate_description(result)
    return result


def validate_description(d):
    """Pure schema/identity checks, not physical-source or tool qualification."""
    # Equality includes all provenance, prerequisites, paths, flags and ordered
    # dependency roles. JSON encoding also distinguishes true from integer 1.
    try:
        supplied = json.dumps(d,sort_keys=True,separators=(',',':'),allow_nan=False)
        expected = json.dumps(_canonical_description(),sort_keys=True,separators=(',',':'),allow_nan=False)
    except (TypeError,ValueError) as error:
        raise ValueError('JSON-safe exact description required') from error
    _need(supplied == expected, 'exact canonical description contract')
    _need(d.get('status') == 'UNRUN_PORTABLE_BUILD_RECIPE' and d.get('execution_authority') is False, 'unrun scope')
    _need(bool(d.get('unresolved_prerequisites')), 'missing unresolved gate')
    paths = [r['path'] for r in d['inputs']]
    _need(len(paths) == len(set(paths)), 'duplicate source path')
    for r in d['inputs']:
        _need(not r['path'].startswith('/') and '..' not in r['path'].split('/') and re.fullmatch('[0-9a-f]{64}',r['sha256']), 'source pin/path')
    g = d['generated_contract']
    _need(g['provider_files'] == _DATA['provider_files'], 'exact provider identities')
    _need(len(g['provider_files']) == 13 and all('/' not in x for x in g['provider_files']), 'provider basenames')
    _need(g['filelist_order'] == {'matrix':_DATA['matrix_filelist'], 'icg':_DATA['icg_filelist']}, 'provider order')
    flat = g['filelist_order']['matrix'] + g['filelist_order']['icg']
    _need(len(flat) == len(set(flat)) == 13 and set(flat) == set(g['provider_files']), 'duplicate/omitted provider')
    for kind,count in [('matrix',193),('icg',7)]:
        names=g['unit_names'][kind]
        _need(len(names)==len(set(names))==count and names == _DATA['unit_names'][kind], 'unit identity/order')
        _need(g['headers'][kind] == _DATA['generated_headers'][kind], 'generated header contract')
    _need(g['fma'] == _DATA['fma'] and len(set(g['fma']['modules'])) == 9, 'full FMA contract')
    _need(g['ABI']['service_instances']==8 and g['ABI']['MACs_per_instance']==512 and g['ABI']['total_MACs']==4096, 'unchanged service size')
    _need(g['ABI']['matrix_input_words']==63 and g['ABI']['matrix_output_words']==533, 'complete snapshot ABI')
    stages=d['stages'];ids=[s['id'] for s in stages];outputs=[x for s in stages for x in s['outputs']]
    _need(len(ids)==len(set(ids)) and len(outputs)==len(set(outputs)), 'duplicate stage/output role')
    literal_outputs=[]
    available = {r['role'] for r in d['inputs']} | set(d['artifacts'])
    for s in stages:
        _need(s.get('unexecuted') is True and isinstance(s['argv'],list) and s['argv'], 'stage is descriptive only')
        _need(s['cwd'] == '{build}' or s['cwd'].startswith('{build}/'), 'build-local cwd')
        _need('..' not in s['cwd'].split('/') and s['preconditions'], 'safe cwd and nonempty preconditions')
        _need(set(s['inputs']) <= available, 'undeclared or forward input role')
        for role in s['inputs']:
            if role in d['artifacts']:
                _need(set(d['artifacts'][role].get('requires_output_roles',[])) <= available, 'unavailable prerequisite output')
        for token in re.findall(r'\{([^{}]+)\}', repr([s['cwd'],s['argv']])):
            _need(token in d['placeholders'], 'undeclared placeholder '+token)
            if token.startswith('artifact:'):
                _need(token.split(':',1)[1] in d['artifacts'], 'missing artifact descriptor')
        if '-o' in s['argv']:literal_outputs.append(s['argv'][s['argv'].index('-o')+1])
        available.update(s['outputs'])
    _need(len(literal_outputs)==len(set(literal_outputs)), 'duplicate output path')
    return True


def validate(description=None):
    """Shared-validator API. This does not establish physical build readiness."""
    return validate_description(describe() if description is None else description)


def verify_supplied_provider_bytes(files):
    """Pure validation of supplied bytes; no path reads or output writes."""
    _need(set(files)==set(_DATA['provider_files']), 'exact provider byte set')
    for name,expected in _DATA['provider_files'].items():
        _need(type(files[name]) is bytes and hashlib.sha256(files[name]).hexdigest()==expected, 'provider byte mismatch '+name)
    _need(sum(map(len,files.values()))==43047,'provider byte count')
    return True


def verify_supplied_generated_units(kind, names):
    _need(kind in _DATA['unit_names'], 'unknown generated type')
    _need(type(names) is list and len(names)==len(set(names)) and names==_DATA['unit_names'][kind], 'exact generated unit order')
    return True
