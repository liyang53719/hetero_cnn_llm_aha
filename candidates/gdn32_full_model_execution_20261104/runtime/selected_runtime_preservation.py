"""Test-only exact inverse of reviewed dependency-selection deltas.
Keeps the pre-selection source fixture and historical preservation hashes intact.
Unknown statements survive the inverse and therefore cannot hide in old proofs.
"""
import ast,copy,hashlib,pathlib
D=pathlib.Path(__file__).resolve().parent
FIXTURE_SHA='d3d60948b3cd1e41756fd423ee863d18e173c6da310d4868b58390f61e8e0c90'
FUNCTIONS={'admit':'f7fa9807ef89d0643ea8bb4202fab17d8ff802f8529bd4cc8c0bbccada2d6edf','manifest':'34eeb8a0c6ba5ce2fb2bf776f6b0494b527f84d6a982e74c6807e30a8e4aa6f3','verify_entry':'296524777f31d8a38d8deddc17acab2c7f2c534832958e536b115d47ad4b8da5','original_archives':'a2cb09c9a971cc0ce4c9db575007ad3c70a0abe0d0f885a68be925f6c17c7ec4','archive_evidence':'038cdb72d0bc6860be66d670833d341e23ae4e1e8bfff1af16908c5bc223858e','verify':'da6b655ca017388bebd38d4f2552ce7b0703d2cc47beb894214904f88f126804','lease':'f0415bda05b68ff606ef745f83bb62126b6165958877a6cca47b0be4e1f07280','import_result':'bf8d464f284ff7e2b91d19cf7fb56fc7f8be9910569f63e7b442392416eff800','run':'9e32dd75a44e2faffe0544fd428711575d9411a3df59046b1f72682e44d6689c'}
IMPORT="_dep_spec=importlib.util.spec_from_file_location('runtime_dependencies',P(__file__).resolve().parent/'runtime_dependencies.py');deps=importlib.util.module_from_spec(_dep_spec);_dep_spec.loader.exec_module(deps)"
def undo_selected_runtime(test,tree):
 tree=copy.deepcopy(tree);raw=(D/'fixtures/runtime_reuse_pre_selection.py.txt').read_bytes()
 test.assertEqual(hashlib.sha256(raw).hexdigest(),FIXTURE_SHA,'frozen pre-selection runtime source')
 original=ast.parse(raw);old={n.name:n for n in original.body if isinstance(n,ast.FunctionDef)}
 for statement in ast.parse(IMPORT).body:
  matches=[n for n in tree.body if ast.dump(n)==ast.dump(statement)]
  test.assertEqual(len(matches),1,'exact selected dependency import');tree.body.remove(matches[0])
 for name,digest in FUNCTIONS.items():
  matches=[n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name==name]
  test.assertEqual(len(matches),1,'one selected runtime function '+name);node=matches[0]
  test.assertEqual(hashlib.sha256(ast.dump(node).encode()).hexdigest(),digest,'exact selected runtime delta '+name)
  if name in old:tree.body[tree.body.index(node)]=old[name]
  else:tree.body.remove(node)
 return tree
