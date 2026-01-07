import os
import sys
import inspect

import traceback
import marshal
from types import FrameType, FunctionType, MethodType, CodeType, ModuleType

import ast
import inspect
import difflib
from pathlib import Path
from bytecode import Bytecode

import axolotl
import axolotl.mode as mc
from .validation import Validater, Mutator
from .instrumenter import Instrumenter
from .logger import get_logger, get_reporter
from .san2patch.model import BaseModel

PATCH_FOLDER = f"{os.getenv('WDIR')}/patch_file"
MAX_RECURSION = 3

## exception trace handler
def except_handler(e: Exception):
    logger = get_logger()
    reporter = get_reporter()
    
    ### origin program except handler blacklist ###
    IGNORE_EXCEPTIONS = [
        'SystemExit', 'KeyboardInterrupt', 'GeneratorExit', 'StopIteration',
        'NotThisMethod', 'SkipTest'
    ]
    IGNORE_EXCEPTION_MSG = [
        'Invalid frequency', 'data type not understood' #pandas exception handler
    ]
    ################################################

    except_name = type(e).__name__
    if (except_name in IGNORE_EXCEPTIONS) or (any(msg in str(e) for msg in IGNORE_EXCEPTION_MSG)):
        mc.safe_mode()
        return

    if e.__traceback__ is None:
        print("No traceback available for this exception.")
        return
    
    if reporter:
        reporter.record_crash_time()
    
    ## info 1 ##
    exception_msg = f"{type(e).__name__} {str(e)}"
    
    # Traceback Logging
    logger.debug(f"Exception : {exception_msg}")

    tb_list = traceback.format_tb(e.__traceback__)

    ## info 2 ## -> full traceback string
    tb_string = "".join(tb_list)
    
    logger.debug("\n" + "="*40 + " FULL TRACEBACK " + "="*40)
    logger.debug(f"\n{tb_string}")
    logger.debug(f"{exception_msg}")
    logger.debug("="*96)

    target_source_env = os.getenv("TARGET_SOURCE") 
    if not target_source_env:
        target_root = Path(os.getcwd()).resolve()
    else:
        target_root = Path(target_source_env).resolve()
    
    tool_root = Path(axolotl.__file__).parent.resolve()
    innerframes = inspect.getinnerframes(e.__traceback__)
    innerframes.reverse()
    outerframes = inspect.getouterframes(e.__traceback__.tb_frame)
    total_frames = innerframes + outerframes
    
    target_frame = None
    
    for frame in total_frames:
        frame_file = Path(frame.filename).resolve()
        if tool_root in frame_file.parents or frame_file == tool_root:
            continue
        if target_root not in frame_file.parents and frame_file.parent != target_root:
            continue    
        if 'site-packages' in str(frame_file) or 'dist-packages' in str(frame_file):
            continue
        if '_libs' in str(frame_file) or frame_file.name.endswith('.pyx') or frame_file.name.endswith('.so'):
            logger.debug(f"Skip compiled/cython frame: {frame_file.name}")
            continue

        target_frame = frame
        break
    
    if target_frame is None:
        logger.error("No target frame found within the project scope.")
        return
    else:
        logger.debug(f"Initial Target found: {target_frame.filename} at line {target_frame.lineno}, func_name {target_frame.function}")
    
    initial_func_name = target_frame.function
    filename = target_frame.filename
    lineno = target_frame.lineno

    # check the target function is inner function or global function
    final_target_name = initial_func_name
    frame_for_args = target_frame

    is_hard_global = False
    try:
        global_candidate = target_frame.frame.f_globals.get(initial_func_name)
        if global_candidate and getattr(global_candidate, "__code__", None) is target_frame.frame.f_code:
            is_hard_global = True
            logger.info(f"[*] '{initial_func_name}' identified as Global via f_globals check. Skipping AST logic.")
    except Exception as e:
        logger.warning(f"[!] Global check failed: {e}")

    if is_hard_global:
        outer_func_name = initial_func_name
    else:
        outer_func_name = get_enclosing_global_function(filename, lineno)

    if outer_func_name and outer_func_name != initial_func_name:
        logger.info(f"[*] Inner Function detected: '{initial_func_name}' is inside '{outer_func_name}'")
        found_outer_frame = None
        current_frame = target_frame.frame.f_back 
        
        while current_frame:
            if current_frame.f_code.co_name == outer_func_name:
                found_outer_frame = current_frame
                break
            current_frame = current_frame.f_back
        
        if found_outer_frame:
            logger.info(f"[*] Outer Frame found in stack. Swapping target to: '{outer_func_name}'")
            final_target_name = outer_func_name
            frame_for_args = found_outer_frame
        else:
            logger.warning(f"[!] Outer function '{outer_func_name}' is not in the stack (Closure pattern). Skipping this target.")
            mc.safe_mode()
            exit(1)
    elif outer_func_name:
         logger.info(f"[*] Target '{initial_func_name}' is already a Global Function.")
    else:
        logger.warning(f"[!] Could not find enclosing function via AST. Keeping '{initial_func_name}'.")
    
    try:
        raw_frame = getattr(frame_for_args, 'frame', frame_for_args)
        module_globals = raw_frame.f_globals
        
        if final_target_name in module_globals:
            real_func_obj = module_globals[final_target_name]
            save_origin_func_code(real_func_obj, final_target_name)
            logger.info(f"Successfully saved source code for: {final_target_name}")
        else:
            logger.error(f"Cannot find '{final_target_name}' in globals. Dynamic extraction required.")
            return

    except Exception as exc:
        logger.error(f"Failed to extract/save source code: {exc}")
        return

    func_name = final_target_name
    
    # 여기서 frame_for_args가 Outer Frame이면 Outer의 인자가, 
    # Inner Frame(Global)이면 본인의 인자가 추출됨 -> Validation 호환성 확보 완료
    args, kwargs = extract_args_kwargs(frame_for_args)
    globals_vars = target_frame.frame.f_globals


    ## 함수 내부 로컬변수들과 함수에서 사용된 글로벌 변수들 추출
    func_code = target_frame.frame.f_code
    locals_vars_dict = target_frame.frame.f_locals

    used_globals = set(func_code.co_names)
    local_vars = set(func_code.co_varnames)

    filtered_globals = {
        k: v for k, v in globals_vars.items()
        if k in used_globals and k not in local_vars
    }
    filtered_globals = {
        k: v for k, v in filtered_globals.items()
        if k not in dir(__builtins__) and k != '__builtins__'
    }
    filtered_locals = {
        k: v for k, v in locals_vars_dict.items()
        if not (isinstance(v, ModuleType) and 'axolotl' in getattr(v, '__file__', ''))
    }


    # san2patch patch generation model
    # TODO: modify parameter
    model = BaseModel(
        project_path = filename,
        project_name = '',

    )

    model.exception_msg = exception_msg
    model.exception_trace = tb_string
    model.target_line = get_targetline_code(filename, lineno)
    model.buggy_code = get_origin_func_code(func_name)

    # ablation3: without dynamic context -> run_wo_dc()
    if reporter:
        with reporter.measure_patch_gen(mode='first'):
            # original / ablation2: without feedback info
            model.run(os.getenv("WDIR"))
            
            # ablation1: without tot
            # model.run_singleton(os.getenv("WDIR"))

            # ablation3: without dynamic context
            # model.run_wo_dc(os.getenv("WDIR"))
    else:
        # original / ablation2: without feedback info
        model.run(os.getenv("WDIR"))

        # ablation1: without tot
        # model.run_singleton(os.getenv("WDIR"))

        # ablation3: without dynamic context
        # model.run_wo_dc(os.getenv("WDIR"))

    ever_pass_validation_part1 = False
    final_success = False

    # feedback recursion 3회
    ### TODO 
    # -> max_recursion parameter로
    # -> base, ablation -> parameter로
    for j in range(MAX_RECURSION):

        if not model.patches or len(model.patches) == 0:
            logger.error("No patches generated by San2Patch model.")
            mc.validation_fail_mode()
            sys.exit(1)
        
        patch_codes_diff = []

        # 후에 val1 통과, val2 실패 구분용
        any_part1_passed_in_round = False

        for i, patch_code in enumerate(model.patches):
            repair_code = patch_code['patched_code']

            # orginal validation part 1
            patch_py = os.path.join(PATCH_FOLDER, f"{func_name}.py")
            patch_file_path = os.path.join(PATCH_FOLDER, f"{func_name}_patch")
            patch_val1_file_path = os.path.join(PATCH_FOLDER, f"{func_name}_val1_patch")
            with open(patch_py, 'w') as f:
                f.write(repair_code)

            logger.info(f'--- Patch Candidate {i} (Round {j}) ---')
            
            diff_list = list(difflib.unified_diff(
                model.buggy_code.strip().splitlines(),
                repair_code.strip().splitlines(),
                fromfile='buggy_func.py',
                tofile='patch_func.py',
                lineterm=''
            ))

            for line in diff_list:
                logger.info(line)

            # ablation2 : (w/o feedback)
            patch_codes_diff.append("\n".join(diff_list))

            sci = Instrumenter()
            sci.throw_exception_when_error = True
            sci.is_script_mode = True

            try:
                with open(patch_py, "r") as f:
                    t = ast.parse(f.read())
                    p_code = compile(t, str(Path(patch_py).resolve()), "exec").co_consts[0]

                if not isinstance(p_code, CodeType):
                    for const in compile(t, str(Path(patch_py).resolve()), "exec").co_consts:
                        if isinstance(const, CodeType) and const.co_name == func_name:
                            p_code = const
                            break
                
                TE_p_code = sci.insert_try_except_for_patchcode(p_code) #try-except만 넣은거

                with open(patch_val1_file_path, 'wb') as patch_file:
                    marshal.dump(p_code, patch_file)
                with open(patch_file_path, 'wb') as patch_file:
                    marshal.dump(TE_p_code, patch_file)
                    
            except Exception as e:
                logger.error(f"Failed to compile patch code_{i}_{j}: {e}")
                # 다음 코드 테스트
                continue

            val = Validater()
            logger.info(f"Validating patch_{i}(feedback_{j})...")
            ############################################
            ## validation part1 : exception avoid test##
            ############################################
            is_valid_part1 = False
            if reporter:
                with reporter.measure_validation():
                    is_valid_part1 = val.validate_patch(patch_val1_file_path, func_name, args, kwargs, globals_vars)
            else:
                is_valid_part1 = val.validate_patch(patch_val1_file_path, func_name, args, kwargs, globals_vars)
            
            if is_valid_part1:
                logger.info(f"Patch_{i}(feedback_{j}) passed validation part1")
                any_part1_passed_in_round = True
                ever_pass_validation_part1 = True

                ## for skip val 2 ##
                # mc.validation_mode()
                # final_success = True
                # break
                ##
            
                ########################################
                ## validation part2 : Regression test ##
                ########################################
                try:
                    #original_code already compile
                    og_bc = get_bytecode(model.buggy_code, func_name)
                    #patch code already compile
                    pc_bc = get_bytecode(repair_code, func_name)
                except Exception as e:
                    logger.error(f"[Val-2] Bytecode conversion failed :{e}")
                    continue
                    
                is_valid_part2 = False
                if reporter:
                    with reporter.measure_validation():
                        is_valid_part2 = val.regression_test(func_name, og_bc, pc_bc, args, kwargs, globals_vars)
                else:
                    is_valid_part2 = val.regression_test(func_name, og_bc, pc_bc, args, kwargs, globals_vars)
                
                if is_valid_part2:
                    logger.info(f"[Val-2] Patch_{i}(feedback_{j}) passed regression tests.")
                    logger.info(f"[Val-R] Patch successful for function '{func_name}' with Patch_{i}(feedback_{j}).")

                    mc.validation_mode()
                    final_success = True
                    break
                else:
                    logger.warning(f"[Val-2] Patch_{i}(feedback_{j}) failed regression tests.")
                    continue

        # val1, val2 모두 통과
        if final_success:
            break

        if j < MAX_RECURSION - 1:
            if not any_part1_passed_in_round:
                logger.error(f"Round {j}: All patches failed validation 1 (Syntax/Runtime Error).")
            else:
                logger.error(f"Round {j}: Patches pass validation 1 but failed validation 2 (REGRESSION test).")
            
            logger.info("Regenerating patches with feedback...")
            
            if reporter:
                with reporter.measure_patch_gen(mode='feedback'):
                    # origin
                    model.feedback_patch_gen(patch_codes_diff)

                    # ablation1: w/o tot
                    # model.feedback_patch_gen_singleton(patch_codes_diff)
            else:
                #origin
                model.feedback_patch_gen(patch_codes_diff)

                # ablation1: w/o tot
                # model.feedback_patch_gen_singleton(patch_codes_diff)
        else:
            logger.error("Max recursion reached.")

    if not final_success:
        if ever_pass_validation_part1:
            # L1통과, L2실패
            logger.error(f"[Val-R] All patches failed validation part2 (REGRESSION test) for function '{func_name}'.")
        else:
            # 아예실패
            logger.error(f"[Val-R]All patches failed validation part1 for function '{func_name}'.")
        mc.validation_fail_mode()
        sys.exit(1)

def get_bytecode(code_str: str, func_name: str) -> Bytecode:
    t = ast.parse(code_str)
    code_obj = compile(t, "<string>", "exec")
    for const in code_obj.co_consts:
        if isinstance(const, CodeType) and const.co_name == func_name:
            return Bytecode.from_code(const)

    
def extract_args_kwargs(frame_info):
    """
    Extracts args and kwargs directly from the stack frame.
    Handles both FrameInfo objects and raw Frame objects.
    """

    frame = getattr(frame_info, 'frame', frame_info)
    arg_info = inspect.getargvalues(frame)
    
    args_dict = {}

    for arg_name in arg_info.args:
        if arg_name in arg_info.locals:
            args_dict[arg_name] = arg_info.locals[arg_name]

    if arg_info.varargs:
        varargs_name = arg_info.varargs
        if varargs_name in arg_info.locals:
            args_dict[varargs_name] = arg_info.locals[varargs_name]

    kwargs_dict = {}
    if arg_info.keywords:
        kw_name = arg_info.keywords
        if kw_name in arg_info.locals:
            kwargs_dict = arg_info.locals[kw_name]

    return args_dict, kwargs_dict

def save_origin_func_code(func_obj, func_name):
    func_code = inspect.getsource(func_obj)
    origin_func_code = os.path.join(PATCH_FOLDER, f"{func_name}_origin.py")

    with open(origin_func_code, 'w') as f:
        f.write(func_code)

def get_origin_func_code(func_name):
    origin_func_code = os.path.join(PATCH_FOLDER, f"{func_name}_origin.py")
    with open(origin_func_code, 'r') as f:
        code = f.read()
    return code

def get_targetline_code(file_path, target_lineno):
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        if 1 <= target_lineno <= len(lines):
            return lines[target_lineno - 1].rstrip('\n')
        else:
            return None
    
def get_enclosing_global_function(file_path, target_lineno):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
    except Exception as e:
        print(f"Error reading file for AST: {e}")
        return None
    finder = EnclosingFuncVisitor(target_lineno)
    finder.visit(tree)
    return finder.global_func_name

class EnclosingFuncVisitor(ast.NodeVisitor):
    def __init__(self, target_lineno):
        self.target_lineno = target_lineno
        self.global_func_name = None
        self.current_global_scope = None

    def visit_FunctionDef(self, node):
        self._check_node(node)

    def visit_AsyncFunctionDef(self, node):
        self._check_node(node)

    def _check_node(self, node):
        is_top_level = (self.current_global_scope is None)
        
        if is_top_level:
            self.current_global_scope = node.name

        start = node.lineno
        end = getattr(node, 'end_lineno', 999999)

        if start <= self.target_lineno <= end:
            if self.global_func_name is None:
                self.global_func_name = self.current_global_scope

        self.generic_visit(node)

        if is_top_level:
            self.current_global_scope = None