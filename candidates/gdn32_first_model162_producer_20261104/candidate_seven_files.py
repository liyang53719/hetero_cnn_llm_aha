"""Candidate byte import/export; old V2 acceptance remains a separate module."""
import pathlib,sys
D=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(D.parent/'split_build_only_20261031'))
from seven_files import CAP,NAMES,need,sha,regular
from pack_model_candidate import verify_candidate_seven
verify=verify_candidate_seven
