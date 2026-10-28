import importlib.util,torch,json
s=importlib.util.spec_from_file_location('diag','independent_reference_runtime_binding_20261028T2300/router_tie_diagnostics_v2.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
torch.set_num_threads(1);i=torch.tensor([[0]],dtype=torch.int64)
for vals,raw_expected,soft_expected in [([1.,0.,-1.],False,False),([0.,0.,-1.],True,True),([0.,-1.e-9,-2.e-9],False,True)]:
 x=torch.tensor([vals],dtype=torch.float32);p=torch.nn.functional.softmax(x,dim=-1,dtype=torch.float)
 if bool(m.boundary(x,i).item())!=raw_expected or bool(m.boundary(p,i).item())!=soft_expected:raise ValueError('tie classification')
print(json.dumps(dict(status='PASS_3_SYNTHETIC_BOUNDARY_CLASSIFICATION_TESTS_ONLY',raw_and_softmax_ties_distinguished=True,actual_model_executed=False)))
