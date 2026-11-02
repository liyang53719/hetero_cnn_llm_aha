"""Exact nonhierarchical terminal words, host classification only.
No compiler/simulator invocation and no assumption of contiguous C++ members.
"""
import argparse
import json
import re
import pathlib
import first_fault_probe as scalar

SCHEMA_SHA = '6df79f9f5c1088c1f79caf90c713aa1cf223cba264c7bbeb8f1845cff29010ba'
PREFIX = 'TransposedDenseDownOwner_io_matrix_result_bits_value_'
MEMBER_PREFIX = 'HostBlockTopV4__DOT__owner__DOT__' + PREFIX
COUNT = 4096

def load_schema(path):
    raw = scalar.read(path, 16384)
    scalar.need(scalar.digest(raw) == SCHEMA_SHA, 'fixed terminal schema bytes')
    return json.loads(raw), raw

def names():
    return [PREFIX+str(r)+'_'+str(c) for r in range(16) for c in range(256)]

def config_bytes():
    return ('`verilator_config\n'+''.join('public_flat_rd -module "QwenOwnerKernel" -var "'+n+'"\n' for n in names())).encode('ascii')

def match_header(raw):
    # Reuse original complete header guard/class validation, on a fixed scalar
    # witness also required by the terminal consumer; do not relax its parser.
    scalar.match_header({'signals':[dict(module='HostBlockTopV4',sv_var='io_resetRequired',instance_path='',symbol_key='HostBlockTopV4__io_resetRequired',width_bits=1)]}, raw)
    cleaned = scalar.mask_comments(raw.decode('ascii'))
    decl = 'class alignas(VL_CACHE_LINE_BYTES) '+scalar.ROOT_TYPE+' final : public VerilatedModule {'
    body = cleaned.split(decl,1)[1].split('\n};',1)[0]
    occurrences = re.findall(r'\b'+re.escape(MEMBER_PREFIX)+r'[A-Za-z0-9_]*\b',body)
    sv_names = names()
    expected = ['HostBlockTopV4__DOT__owner__DOT__'+n for n in sv_names]
    scalar.need(len(occurrences)==COUNT and set(occurrences)==set(expected), 'exact unique terminal member inventory')
    declarations = {}
    pat = re.compile(r'^\s*(CData|SData|IData|QData)/\*(\d+):(\d+)\*/\s+('+re.escape(MEMBER_PREFIX)+r'\d+_\d+);\s*$',re.M)
    for m in pat.finditer(body):
        scalar.need(m[1]=='IData' and m[2]=='31' and m[3]=='0', 'terminal word exact unsigned 32-bit declaration')
        scalar.need(m[4] not in declarations, 'duplicate terminal declaration')
        declarations[m[4]]=m[0].strip()
    scalar.need(set(declarations)==set(expected), 'all terminal declarations required')
    return [dict(index=i,row=i//256,column=i%256,sv_var=sv_names[i],member=n,width_bits=32,declaration=declarations[n]) for i,n in enumerate(expected)]

def accessor_bytes(mappings):
    scalar.need(len(mappings)==COUNT, 'complete terminal accessor')
    lines=['#pragma once','#include <cstddef>','#include <cstdint>','#include <cstdlib>','#include "VHostBlockTopV4.h"','#include "VHostBlockTopV4___024root.h"','namespace readonly_terminal_finite_access {','inline constexpr std::size_t word_count = 4096;','inline constexpr char schema_sha256[] = "'+SCHEMA_SHA+'";','inline std::uint32_t word(const VHostBlockTopV4& dut, std::size_t index) noexcept {','  const VHostBlockTopV4___024root* const root = dut.rootp;','  switch (index) {']
    for i,m in enumerate(mappings):
        scalar.need(m['index']==i and m['member']==MEMBER_PREFIX+str(i//256)+'_'+str(i%256), 'fixed accessor order')
        lines.append('    case '+str(i)+': return static_cast<std::uint32_t>(root->'+m['member']+');')
    lines += ['    default: std::abort();','  }','}','} // namespace readonly_terminal_finite_access','']
    return '\n'.join(lines).encode('ascii')

def generate(schema_path, config_path, root_header, accessor_path, evidence_path):
    _,schema_raw=load_schema(schema_path); config_raw=scalar.read(config_path,1<<20)
    scalar.need(config_raw==config_bytes(),'exact terminal read-only config')
    root_raw=scalar.read(root_header,scalar.HEADER_CAP)
    scalar.need(pathlib.Path(root_header).name==scalar.ROOT_TYPE+'.h','actual root header basename')
    mappings=match_header(root_raw); access_raw=accessor_bytes(mappings)
    out=scalar.canonical(accessor_path,False); ev=scalar.canonical(evidence_path,False)
    scalar.need(out!=ev and out.name=='readonly_terminal_finite_access.hpp','distinct fixed terminal outputs')
    result=dict(schema='ACTUAL_TERMINAL_FINITE_ACCESSOR_EVIDENCE_V1',scope='READ_ONLY_TERMINAL_CLASSIFICATION_NOT_NUMERICAL_ACCEPTANCE',schema_input=scalar.pin(schema_path,schema_raw),config=scalar.pin(config_path,config_raw,True),root_header=scalar.pin(root_header,root_raw),accessor=scalar.pin(out,access_raw,True),mappings=mappings,word_count=COUNT,reads_hier_child_internals=False,extra_eval_or_clock=False,output_raw_words=False)
    data=(json.dumps(result,indent=2)+'\n').encode();scalar.need(len(data)<=4<<20,'bounded complete terminal evidence')
    with out.open('xb') as f:f.write(access_raw)
    with ev.open('xb') as f:f.write(data)
    return result

def main():
    p=argparse.ArgumentParser();s=p.add_subparsers(dest='command',required=True)
    c=s.add_parser('config');c.add_argument('--schema',required=True);c.add_argument('--output',required=True)
    g=s.add_parser('generate')
    for n in ('schema','config','root-header','accessor','evidence'):g.add_argument('--'+n,required=True)
    a=p.parse_args()
    if a.command=='config':
        load_schema(a.schema);out=scalar.canonical(a.output,False)
        with out.open('xb') as f:f.write(config_bytes())
    else:generate(a.schema,a.config,a.root_header,a.accessor,a.evidence)
    print('TERMINAL_FINITE_ACCESSOR_GENERATED_NOT_EXECUTION_ACCEPTANCE')
if __name__=='__main__':main()
