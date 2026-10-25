"""Descriptor-safe diagnostic inventory. Never call unknown repr/getters.

The dictionary of an exact ModuleType is the source of names/values. Unknown
members are represented by object and type IDs, not dynamically derived names.
"""
import types

KINDS=((type(None),'none'),(str,'str'),(bool,'bool'),(int,'int'),(float,'float'),
       (types.ModuleType,'module'),(types.FunctionType,'python_function'),
       (types.BuiltinFunctionType,'builtin_function'),(type,'builtin_type'),
       (types.GetSetDescriptorType,'getset_descriptor'),
       (types.MemberDescriptorType,'member_descriptor'),
       (types.MethodDescriptorType,'method_descriptor'),
       (types.WrapperDescriptorType,'wrapper_descriptor'),
       (ValueError,'value_error'),(TypeError,'type_error'),(RuntimeError,'runtime_error'))


def value_record(value):
    actual=type(value)
    label=next((label for kind,label in KINDS if actual is kind),'other')
    result={'object_id':hex(id(value)),'type_object_id':hex(id(actual)),'builtin_kind':label}
    if actual is str or actual is bool or value is None:
        result['scalar']=value
    return result


def snapshot(modules,names):
    rows=[]
    for name in names:
        item=modules.get(name)
        row={'module_key':name,'present':item is not None,'object':value_record(item),'members':[],'errors':[]}
        if type(item) is types.ModuleType:
            try:
                members=list(vars(item).items())
                for key,value in members:
                    row['members'].append({'name':key if type(key) is str else None,
                                           'name_metadata':value_record(key),'value':value_record(value)})
            except Exception as error:
                row['errors'].append({'kind':'member_collection_error','error':value_record(error)})
        rows.append(row)
    return rows
