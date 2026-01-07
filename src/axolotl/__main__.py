import sys
from pathlib import Path
import os
import glob
import subprocess
import psutil
import pickle
import shutil
import argparse

from .loader import RuntimeAPRFileMatcher
from .checkpoint import Checkpoint
from .logger import setup_logger, get_reporter

# The intended usage is:
#
#   axolotl.py [options] (script | -m module [module_args...])
#
# but argparse doesn't seem to support this.  We work around that by only
# showing it what we need.
ap = argparse.ArgumentParser(prog='axolotl')
ap.add_argument('--wdir', type=Path, required=True, help="specify working directory (REQUIRED)")
ap.add_argument('--source', type=str, help="target project root directory to instrument")

# Custom options for axolotl
ap.add_argument('--throw-exception', action='store_true', help="throw exception when an error is occured")
ap.add_argument('--llm_model', type=str, default='gpt5', choices=['gpt5', 'qwen', 'llama'], 
                help="Select LLM mode: 'gpt5', 'qwen', or 'llama'")

g = ap.add_mutually_exclusive_group(required=True)
g.add_argument('-m', dest='module', nargs=1, help="run given module as __main__")
g.add_argument('script', nargs='?', type=Path, help="the script to run")
ap.add_argument('script_or_module_args', nargs=argparse.REMAINDER)
ap.add_argument('--ignore-repair', action='store_true', help="run the input file as the basic interpreter")

if '-m' in sys.argv:  # work around exclusive group not handled properly
    minus_m = sys.argv.index('-m')
    args = ap.parse_args(sys.argv[1 : minus_m + 2])
    args.script_or_module_args = sys.argv[minus_m + 2 :]
else:
    args = ap.parse_args(sys.argv[1:])

wdir = args.wdir.resolve()
if args.llm_model:
    wdir = wdir / args.llm_model
os.environ["WDIR"] = str(wdir)
os.makedirs(wdir, exist_ok=True)

def clean_and_create_directory(dir):
    if os.path.exists(dir):
        files = glob.glob(f'{dir}/*')
        for file in files:
            try:
                os.remove(file)
            except IsADirectoryError:
                shutil.rmtree(file)
    else:
        os.makedirs(dir, exist_ok=True)

clean_and_create_directory(f'{wdir}/instrumented')
clean_and_create_directory(f'{wdir}/patch_file')
clean_and_create_directory(f'{wdir}/log')

logger = setup_logger(str(wdir), vars(args)) 
reporter = get_reporter()

logger.info(f"Axolotl Started! Working Directory: {wdir}")

file_matcher = RuntimeAPRFileMatcher()

# set instrumentation target
if args.source:
    target_root = Path(args.source).resolve()
    if target_root.exists():
        file_matcher.addSource(str(target_root))
        logger.info(f"[*] Instrumentation target set to: {target_root}")
    else:
        logger.warning(f"[!] Warning: Specified source path does not exist: {target_root}")
else:
    logger.warning("[!] Warning: No --source provided. Instrumentation might not work correctly.")
    if args.script:
        file_matcher.addSource(str(Path(args.script).resolve().parent))
    else:
        file_matcher.addSource(os.getcwd())

# save file matcher state
file_matcher_path = f'{wdir}/tmp/axolotl_file_matcher.pkl'
os.makedirs(f'{wdir}/tmp', exist_ok=True)

with open(file_matcher_path, "wb") as f:
    pickle.dump(file_matcher, f)
os.environ["AXOLOTL_FILE_MATCHER"] = file_matcher_path

# initialize mode
with open(f'{wdir}/process_mode', 'w') as f:
    f.write('0')
os.chmod(f'{wdir}/process_mode', 0o666)

# initialize mutation_count## 필요한지 확인필요 대기 TODO
# with open(f'{wdir}/mutation/mutation_count', 'w') as f:
#     f.write('0')
# os.chmod(f'{wdir}/mutation/mutation_count', 0o666)

criu = Checkpoint(str(wdir))

current_file_path = Path(__file__).resolve().parent
submodule_script = current_file_path / 'submodule.py'

if not submodule_script.exists():
    logger.error(f"Error: {submodule_script} not found.")
    sys.exit(1)

## for deliver target project dir for pytest
env = os.environ.copy()
if args.source:
    env["TARGET_PROJECT_ROOT"] = str(Path(args.source).resolve())

if args.script:
    proc = subprocess.Popen(['python3',str(submodule_script), 'script', args.script], env=env)
else:
    module_name = args.module[0]
    module_args = args.script_or_module_args
    proc = subprocess.Popen(['python3', str(submodule_script), 'module', module_name, *module_args], env=env)
proc = psutil.Process(proc.pid)


logger.info(f"[CRIU] Storing initial checkpoint for PID: {proc.pid}")
criu.store_checkpoint(proc,f'{wdir}/checkpoints{criu.restore_num}')

logger.info("[CRIU] Entering CRIU monitoring loop...")
    
criu.criu_loop(proc)

if reporter:
    reporter.end_after_validate_timer()
    reporter.save_report()

logger.info("[Main] Axolotl process completed.")