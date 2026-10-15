import ast
import builtins
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from candidates.qwen2_qk_aten_reduction_candidate import model,probe,source_closure

class ClosureTests(unittest.TestCase):
    def test_cold_with_all_work_and_old_untracked_sources_masked(self):
        original=Path.open
        def guarded(path,*args,**kwargs):
            text=str(path)
            if '/work/' in text or '/qwen2_fullblock_recovery/' in text or '/qwen2_fresh_reference_recovery_m128/' in text:
                raise AssertionError('forbidden legacy/work source access')
            return original(path,*args,**kwargs)
        with patch.object(Path,'open',guarded):
            self.assertEqual(probe.run(),{'status':'NOT_EXECUTED'})
            self.assertEqual(len(source_closure.snapshot()),39)
    def test_new_entry_has_no_old_result_inventory(self):
        source=Path(probe.__file__).read_text()
        self.assertNotIn("oldprobe.OLD/'RESULT.json'",source)
        self.assertNotIn('source_sha256_before',source)
        self.assertNotIn('freeze_path',source)
        self.assertNotIn("previous['selected_rows']",source)
        self.assertNotEqual(probe.OUT.name,'local01')
    def test_fixed_selection_matches_prior_scope_without_private_file(self):
        rows=set(probe.SELECTED_PROBABILITY_ROWS)
        self.assertEqual(len(rows),16)
        self.assertEqual(sum(t+1 for h,t in rows),1796)
    def test_actual_repo_python_imports_are_in_tracked_snapshot(self):
        root=model.ROOT;own=model.HERE;allowed=set(source_closure.snapshot())
        todo=list(own.glob('*.py'));seen=set()
        while todo:
            path=todo.pop()
            if path in seen:continue
            seen.add(path)
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node,ast.Import):names=[a.name for a in node.names]
                elif isinstance(node,ast.ImportFrom):
                    if node.level:
                        base=list(path.relative_to(root).with_suffix('').parts)[:-node.level]
                        names=['.'.join(base+([node.module] if node.module else [])+[a.name]) for a in node.names]
                        if node.module:names+=['.'.join(base+[node.module])]
                    else:names=[node.module or '']+[str(node.module)+'.'+a.name for a in node.names]
                else:continue
                for name in names:
                    target=root/(name.replace('.','/')+'.py')
                    if target.is_file() and target not in seen:
                        if target.parent!=own:self.assertIn(str(target.relative_to(root)),allowed)
                        todo.append(target)
    def test_changed_pin_fails_closed(self):
        original=source_closure.MANIFEST.read_text
        data=json.loads(source_closure.MANIFEST.read_text());first=next(iter(data['tracked_sources']))
        data['tracked_sources'][first]='0'*64
        actual_read=Path.read_text
        def fake(path,*args,**kwargs):return json.dumps(data) if path==source_closure.MANIFEST else actual_read(path,*args,**kwargs)
        with patch.object(Path,'read_text',fake):
            with self.assertRaises(ValueError):source_closure.snapshot()
if __name__=='__main__':unittest.main()
