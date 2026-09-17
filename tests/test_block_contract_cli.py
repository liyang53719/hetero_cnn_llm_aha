"""Exercise CLI failure exit codes and actual pack/readback artifacts."""
from pathlib import Path
import json
import subprocess
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'scripts/block_contract_tools.py'


@pytest.mark.parametrize('optimized',[False,True])
def test_command_cli(optimized):
    prefix=[sys.executable,*(['-O'] if optimized else []),str(SCRIPT)]
    ok=subprocess.run([*prefix,'control','--count','588'],capture_output=True,text=True)
    assert ok.returncode==0
    data=json.loads(ok.stdout)
    assert data['completed']==588 and not data['rtl_execution']
    bad=subprocess.run([*prefix,'control','--count','65536'],capture_output=True,text=True)
    assert bad.returncode==2 and 'CONTRACT_REJECTED' in bad.stderr


def test_pack_cli_and_existing_output_failure(tmp_path):
    import struct
    source=tmp_path/'s';source.write_bytes(struct.pack('<6f',1,2,3,4,5,6))
    contract=tmp_path/'c.json';contract.write_text(json.dumps(dict(source_rows=2,source_columns=3,transpose=True)))
    out=tmp_path/'pack'
    args=[sys.executable,str(SCRIPT),'pack',str(source),str(out),str(contract)]
    ok=subprocess.run(args,capture_output=True,text=True)
    assert ok.returncode==0 and json.loads(ok.stdout)['elements']==6
    bad=subprocess.run(args,capture_output=True,text=True)
    assert bad.returncode==2 and (out/'manifest.json').is_file()
    read=subprocess.run([sys.executable,str(SCRIPT),'readback',str(source),str(out),str(contract)],capture_output=True,text=True)
    assert read.returncode==0
