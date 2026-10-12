"""Synthetic metadata binding tests; no payload download or official forward."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from .input_fixture import select_prefix_tensors, WEIGHTS, WIDTHS
from . import input_fixture as fixture


def metadata(rows=16):
    payload = dict(model_id='fixed-model', revision='fixed-revision', tensors=[])
    manifest = dict(model_id='fixed-model', revision='fixed-revision', query_tokens=rows,
                    parameters={}, tensors={}, cases=[])
    for role, name in WEIGHTS.items():
        shape = [1024] if role == 'input_norm' else [WIDTHS[role], 1024]
        entry = dict(local_name=name, shape=shape, dtype='BF16',
                     bytes=2048 if role == 'input_norm' else WIDTHS[role]*2048, sha256='a'*64)
        payload['tensors'].append(entry)
        manifest['parameters']['layers.3.'+name] = deepcopy(entry)
    for phase in ('cold', 'carried'):
        name = phase+str(rows)
        refs = {role: name+'.'+role for role in ('hidden', *WIDTHS)}
        for role,key in refs.items():
            manifest['tensors'][key] = dict(shape=[1, rows, WIDTHS.get(role, 1024)], dtype='BF16')
        modules = {'input_layernorm': dict(input={'args':[{'tensor':refs['hidden']}]},
                                          output={'result':{'tensor':refs['input_norm']}})}
        for role in ('packed_q_gate', 'k', 'v'):
            modules[WEIGHTS[role].removesuffix('.weight')] = dict(
                input={'args':[{'tensor':refs['input_norm']}]}, output={'result':{'tensor':refs[role]}})
        manifest['cases'].append(dict(name=name, input=refs['hidden'], module_boundaries=modules))
    return manifest,payload


class FixtureTests(unittest.TestCase):
    def test_complete_shapes_bind_original_hidden_and_native_nodes(self):
        for rows in (16,128):
            manifest,payload=metadata(rows)
            selected=select_prefix_tensors(manifest,payload)
            self.assertEqual(len(selected),2)
            self.assertEqual(selected[0]['hidden'],'cold'+str(rows)+'.hidden')
            self.assertEqual(set(selected[0]['references']),set(WIDTHS))

    def test_reject_reference_input_substitution_and_cross_case_source(self):
        for role in ('input_layernorm','self_attn.q_proj','self_attn.k_proj','self_attn.v_proj'):
            manifest,payload=metadata()
            manifest['cases'][0]['module_boundaries'][role]['input']['args']=[{'tensor':'carried16.input_norm'}]
            with self.subTest(role=role),self.assertRaises(ValueError):
                select_prefix_tensors(manifest,payload)

    def test_reject_wrong_full_shape_and_dtype(self):
        for key,change in (('cold16.packed_q_gate',{'shape':[1,16,2048]}),
                           ('cold16.k',{'shape':[1,16,4096]}),
                           ('cold16.v',{'dtype':'F32'}),('cold16.hidden',{'shape':[1,1,1024]})):
            manifest,payload=metadata()
            manifest['tensors'][key].update(change)
            with self.subTest(key=key),self.assertRaises(ValueError):
                select_prefix_tensors(manifest,payload)

    def test_reject_parameter_and_checkpoint_drift(self):
        for change in (lambda m:m.update(revision='changed'),
                       lambda m:m['parameters']['layers.3.self_attn.q_proj.weight'].update(sha256='b'*64),
                       lambda m:m['parameters']['layers.3.input_layernorm.weight'].update(dtype='F32')):
            manifest,payload=metadata();change(manifest)
            with self.assertRaises(ValueError):select_prefix_tensors(manifest,payload)

    def test_missing_actual_node_is_not_fabricated(self):
        manifest,payload=metadata()
        del manifest['cases'][1]['module_boundaries']['self_attn.v_proj']
        with self.assertRaises(KeyError):select_prefix_tensors(manifest,payload)

    def test_manifest_identity_cannot_be_shadowed_by_dependency_loop(self):
        # This isolates loader metadata bookkeeping; complete capture/payload
        # validators have their own tests and are explicitly mocked here.
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); directory=root/'capture'; directory.mkdir()
            payload_dir=root/'payload';payload_dir.mkdir()
            params=json.loads((fixture.ROOT/'candidates/qwen35_attention_prefill/projection_profile.json').read_text())
            profile=root/'candidates/qwen35_attention_prefill/projection_profile.json'
            profile.parent.mkdir(parents=True);profile.write_text(json.dumps(params))
            manifest,payload=metadata()
            environment={k:v for k,v in params['backend'].items() if k not in ('torch','transformers','framework_revision')}
            environment.update(variant='baseline',eval=True,inference=True,
                packages={k:params['backend'][k] for k in ('torch','transformers')})
            dependency=root/'last_runtime.txt';dependency.write_bytes(b'distinct dependency')
            record=dict(path=str(dependency),bytes=dependency.stat().st_size,sha256=fixture.sha(dependency.read_bytes()))
            manifest.update(environment=environment,framework_revision=params['backend']['framework_revision'],
                source_files={'first':record},runtime_files={'last':record},case_identity='metadata_test_only')
            (payload_dir/'manifest.json').write_text(json.dumps(payload))
            original={name:b'weight' for name in WEIGHTS.values()}
            with patch.object(fixture.capture,'validate_manifest'), patch.object(fixture.capture,'recover_tensor_journal',
                    return_value={'tensors':manifest['tensors'],'ignored_unterminated_tail_bytes':0}),\
                    patch('heteronpu.pinned_block_payload.load_payload',return_value=(payload,original)),\
                    patch.object(fixture,'read_tensor',return_value=bytes(16*2048)):
                manifest_path=directory/'manifest.json';manifest_path.write_text(json.dumps(manifest))
                _,_,_,identity=fixture.load_fixture(directory,payload_dir,root)
                self.assertEqual(identity['capture_manifest_sha256'],fixture.sha(manifest_path.read_bytes()))
                self.assertNotEqual(identity['capture_manifest_sha256'],record['sha256'])
                dependency.write_bytes(b'tampered dependency')
                with self.assertRaisesRegex(ValueError,'dependency changed'):
                    fixture.load_fixture(directory,payload_dir,root)


if __name__=='__main__':unittest.main()
