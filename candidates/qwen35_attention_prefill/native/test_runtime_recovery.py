"""Closed path/metadata controls only; dummy bytes are not runtime validation."""
from pathlib import Path
import tempfile
import unittest
from . import capture as c

class RuntimeArtifactPathTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.runtime=self.root/'work/job/runtime02';self.runtime.mkdir(parents=True)

    def file(self, relative, **metadata):
        path=self.root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'path-only-test')
        return dict(path=relative, **metadata)

    def recovery(self):
        records={}
        for name,(scope,suffix,size,digest) in c._RECOVERED_RUNTIME_EXTERNAL.items():
            path=(self.root if scope=='repository' else self.runtime.parent)/suffix
            records[name]=self.file(str(path.relative_to(self.root)),bytes=size,sha256=digest)
        return dict(artifacts=records,package_dependency_closure_verified=True)

    def test_all_46_fixed_records_and_installed_file_paths(self):
        receipt=self.recovery();receipt['artifacts']['installed:a']=self.file('work/job/runtime02/site-packages/a.py')
        self.assertEqual(len(c.validate_runtime_layout(self.root,self.runtime,receipt)),47)
        self.assertEqual(len(c._RECOVERED_RUNTIME_EXTERNAL),46)

    def test_unknown_category_and_wrong_script_location_rejected(self):
        record=self.file('scripts/arbitrary.py')
        for name in ('unknown','backend_runner_source','wheel:unapproved',''):
            with self.subTest(name=name),self.assertRaises(ValueError):c.runtime_artifact_path(self.root,self.runtime,name,record)

    def test_absolute_parent_symlink_and_other_job_rejected(self):
        good=self.file('work/job/runtime02/a')
        for path in (str(self.root/good['path']),'../escape','work/job/runtime02/../runtime02/a'):
            with self.assertRaises(ValueError):c.runtime_artifact_path(self.root,self.runtime,'x',dict(path=path))
        link=self.runtime/'link';link.symlink_to(self.root/good['path'])
        with self.assertRaises(ValueError):c.runtime_artifact_path(self.root,self.runtime,'x',dict(path=str(link.relative_to(self.root))))
        parent=self.runtime/'alias';parent.symlink_to(self.runtime,target_is_directory=True)
        with self.assertRaises(ValueError):c.runtime_artifact_path(self.root,self.runtime,'x',dict(path='work/job/runtime02/alias/a'))
        other=self.file('work/other/runtime_dependency_recovery/network.jsonl')
        with self.assertRaises(ValueError):c.runtime_artifact_path(self.root,self.runtime,'acquisition_provenance:source_ledger',other)

    def test_original_hash_and_size_metadata_cannot_be_relabelled(self):
        receipt=self.recovery();name=next(iter(receipt['artifacts']));record=receipt['artifacts'][name]
        for update in ({'bytes':True},{'bytes':record['bytes']+1},{'sha256':'0'*64},
                       {'path':'work/job/runtime02/relabelled'}):
            if 'path' in update:self.file(update['path'])
            with self.assertRaises(ValueError):c.runtime_artifact_path(self.root,self.runtime,name,{**record,**update})

    def test_missing_provenance_record_or_all_records_is_rejected(self):
        receipt=self.recovery();del receipt['artifacts'][next(iter(receipt['artifacts']))]
        with self.assertRaises(ValueError):c.validate_runtime_layout(self.root,self.runtime,receipt)
        receipt['artifacts']={'installed:a':self.file('work/job/runtime02/a')}
        with self.assertRaises(ValueError):c.validate_runtime_layout(self.root,self.runtime,receipt)

    def test_legacy_in_runtime_only_receipt_and_duplicate_path(self):
        record=self.file('work/job/runtime02/a');receipt={'artifacts':{'a':record}}
        self.assertEqual(len(c.validate_runtime_layout(self.root,self.runtime,receipt)),1)
        receipt['artifacts']['b']=record
        with self.assertRaises(ValueError):c.validate_runtime_layout(self.root,self.runtime,receipt)

    def test_seven_fixed_installed_provenance_alias_pairs(self):
        receipt=self.recovery()
        for suffix,(names,size,digest) in c._RECOVERED_RUNTIME_ALIASES.items():
            record=self.file('work/job/runtime02/'+suffix,bytes=size,sha256=digest)
            for name in names:receipt['artifacts'][name]=dict(record)
        self.assertEqual(len(c._RECOVERED_RUNTIME_ALIASES),7)
        self.assertEqual(len(c.validate_runtime_layout(self.root,self.runtime,receipt)),60)

    def test_known_alias_changed_name_size_hash_or_extra_alias_rejected(self):
        suffix,(names,size,digest)=next(iter(c._RECOVERED_RUNTIME_ALIASES.items()))
        record=self.file('work/job/runtime02/'+suffix,bytes=size,sha256=digest)
        good={name:dict(record) for name in names}
        for changed in ({names[0]:record,'unknown':record},
                        {**good,names[0]:{**record,'bytes':size+1}},
                        {**good,names[0]:{**record,'sha256':'0'*64}},
                        {**good,'extra':record}):
            with self.assertRaises(ValueError):c.validate_runtime_layout(self.root,self.runtime,{'artifacts':changed})

    def test_missing_file_and_runtime_outside_root_rejected(self):
        with self.assertRaises(FileNotFoundError):c.runtime_artifact_path(self.root,self.runtime,'x',dict(path='missing'))
        with self.assertRaises(ValueError):c.runtime_artifact_path(self.runtime,self.root,'x',self.file('work/job/runtime02/a'))
