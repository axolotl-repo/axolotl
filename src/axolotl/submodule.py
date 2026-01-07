import sys
import ast
from pathlib import Path
from typing import Any, Dict
import os
import runpy
import pickle
import traceback

from axolotl.instrumenter import Instrumenter
from axolotl.loader import RuntimeAPRFileMatcher, RuntimeAPRImportManager
from axolotl.logger import setup_logger, get_logger

INST_BLACKLIST = ['test', 'blib2to3', '__init__', 'tests',
                  'managers', # pandas
                  'jsinterp', 'extractor' # youtube-dl
                ]

def load_file_matcher():
    file_matcher_path = os.getenv("AXOLOTL_FILE_MATCHER", None)
    if file_matcher_path and os.path.exists(file_matcher_path):
        with open(file_matcher_path, "rb") as f:
            return pickle.load(f)
    return RuntimeAPRFileMatcher() 

def run_script_mode(file_path):
    logger = get_logger()
    file_matcher = load_file_matcher()
    sci = Instrumenter()

    sci.throw_exception_when_error = True
    sci.is_script_mode = True

    # python 'globals' for the script being executed
    script_globals: Dict[Any, Any] = dict()

    # needed so that the script being invoked behaves like the main one
    script_globals['__name__'] = '__main__'
    script_globals['__file__'] = file_path
    script_globals['axolotl'] = sys.modules.get('axolotl')
    
    with open(file_path, "r") as f:
        t = ast.parse(f.read())
        code = compile(t, str(Path(file_path).resolve()), "exec")

        code = sci.insert_try_except(code)
        logger.debug("Instrumentation complete for script.")

    with RuntimeAPRImportManager(sci, file_matcher):
        exec(code, script_globals)

def run_module_mode(module_name):
    logger=get_logger()
    file_matcher = load_file_matcher()
    sci = Instrumenter()

    sys.argv = sys.argv[3:]
    for kw in INST_BLACKLIST:
        file_matcher.addExcludeKeyword(kw)

    try:
        with RuntimeAPRImportManager(sci, file_matcher):
            runpy.run_module(module_name, run_name='__main__', alter_sys=True)
    except Exception as e:
        logger.error(f"[Module Mode] Execution failed: ")
        logger.error("="*60)
        logger.error(f"CRITICAL ERROR: {type(e).__name__}: {e}")
        logger.error(traceback.format_exc())
        logger.error("="*60)


if __name__ == '__main__':
    wdir = os.getenv("WDIR")
    if wdir:
        setup_logger(wdir)
    
    logger = get_logger()
    
    if len(sys.argv) < 3:
        logger.error("Invalid arguments passed to submodule.")
        sys.exit(1)

    target_source = os.getenv("TARGET_PROJECT_ROOT")
    if target_source:
        target_path = Path(target_source).resolve()
        if target_path.exists():
            os.chdir(str(target_path))

    mode = sys.argv[1]

    if mode == 'script':
        target_script = sys.argv[2]
        run_script_mode(target_script)
    elif mode == 'module':
        target_module = sys.argv[2]
        run_module_mode(target_module)
    else:
        logger.error(f"Unknown mode: {mode}")
        sys.exit(1)