from types import CodeType
from bytecode import Instr, Bytecode, Label, dump_bytecode, Compare, bytecode
import sys
import marshal
import os

PYTHON_VERSION = sys.version_info[:2]
EXCLUDED_FUNC_NAMES = ["print", "len", "range", "set", "lru_cache", "kwlist", "DOTALL"]

class Instrumenter:
    def __init__(self, is_script_mode: bool = False, throw_exception_when_error: bool = False):
        self.is_script_mode = is_script_mode
        self.throw_exception_when_error = throw_exception_when_error
        self.code_stack = []

    def insert_try_except(self, code: CodeType):
        bc = Bytecode.from_code(code)
        cur_lineno = code.co_firstlineno

        is_global = code.co_name == '<module>' 
        # is_class = self.is_class_code(code)

        # Skip if already instrumented
        if isinstance(bc[0], Instr) and bc[0].name == 'LOAD_CONST' and bc[0].arg == '__axolotl__':
            return code

        new_bc = [Instr('LOAD_CONST', '__axolotl__', lineno=1)]

        # import axolotl.mode as mc
        new_bc.append(Instr('LOAD_CONST', 0, lineno=cur_lineno))
        new_bc.append(Instr('LOAD_CONST', None, lineno=cur_lineno))
        new_bc.append(Instr('IMPORT_NAME', 'axolotl.mode', lineno=cur_lineno))
        new_bc.append(Instr('IMPORT_FROM', 'mode', lineno=cur_lineno))
        new_bc.append(Instr('STORE_FAST', '__ax_mc', lineno=cur_lineno))
        new_bc.append(Instr('POP_TOP', lineno=cur_lineno))

        # import axolotl.repair as re
        new_bc.append(Instr('LOAD_CONST', 0, lineno=cur_lineno))
        new_bc.append(Instr('LOAD_CONST', None, lineno=cur_lineno))
        new_bc.append(Instr('IMPORT_NAME', 'axolotl.repair', lineno=cur_lineno))
        new_bc.append(Instr('IMPORT_FROM', 'repair', lineno=cur_lineno))
        new_bc.append(Instr('STORE_FAST', '__ax_re', lineno=cur_lineno))
        new_bc.append(Instr('POP_TOP', lineno=cur_lineno))

        # import axolotl.patch as pc
        new_bc.append(Instr('LOAD_CONST', 0, lineno=cur_lineno))
        new_bc.append(Instr('LOAD_CONST', None, lineno=cur_lineno))
        new_bc.append(Instr('IMPORT_NAME', 'axolotl.patch', lineno=cur_lineno))
        new_bc.append(Instr('IMPORT_FROM', 'patch', lineno=cur_lineno))
        new_bc.append(Instr('STORE_FAST', '__ax_pc', lineno=cur_lineno))
        new_bc.append(Instr('POP_TOP', lineno=cur_lineno))

        # import axolotl.validation as val
        new_bc.append(Instr('LOAD_CONST', 0, lineno=cur_lineno))
        new_bc.append(Instr('LOAD_CONST', None, lineno=cur_lineno))
        new_bc.append(Instr('IMPORT_NAME', 'axolotl.validation', lineno=cur_lineno))
        new_bc.append(Instr('IMPORT_FROM', 'validation', lineno=cur_lineno))
        new_bc.append(Instr('STORE_FAST', '__ax_val', lineno=cur_lineno))
        new_bc.append(Instr('POP_TOP', lineno=cur_lineno))

        # 단일 script일떄
        if not is_global:
            func_name = code.co_name
            argcount = code.co_argcount
            arg = code.co_varnames[:code.co_argcount]
            kwargscount = code.co_kwonlyargcount
            kwargs = code.co_varnames[code.co_argcount:code.co_argcount + code.co_kwonlyargcount]

            patch_not_exist_label = Label()
            safe_mode_label = Label()

            patch_block = [
                Instr("LOAD_FAST", "__ax_pc", lineno=cur_lineno),
                Instr("LOAD_METHOD", "func_patch_exist", lineno=cur_lineno),
                Instr("LOAD_CONST", func_name, lineno=cur_lineno),
                Instr("CALL_METHOD", 1, lineno=cur_lineno),
                Instr("POP_JUMP_IF_FALSE", patch_not_exist_label, lineno=cur_lineno),

                ## 여기부터 mutation_input 적용추가
                # mode = mc.mode_check()
                Instr("LOAD_FAST", "__ax_mc", lineno=cur_lineno),
                Instr("LOAD_METHOD", "mode_check", lineno=cur_lineno),
                Instr("CALL_METHOD", 0, lineno=cur_lineno),
                Instr("STORE_FAST", "mode", lineno=cur_lineno),

                Instr("LOAD_FAST", "mode", lineno=cur_lineno),
                Instr("LOAD_CONST", '0', lineno=cur_lineno),
                Instr("COMPARE_OP", Compare.EQ, lineno=cur_lineno),
                Instr("POP_JUMP_IF_TRUE", safe_mode_label, lineno=cur_lineno),
                Instr('JUMP_FORWARD', patch_not_exist_label, lineno=cur_lineno)         
            ]
            patch_block.extend([
                safe_mode_label,
                Instr("LOAD_FAST", "__ax_pc", lineno=cur_lineno),
                Instr("LOAD_METHOD", "patched_func", lineno=cur_lineno),
                Instr("LOAD_CONST", func_name, lineno=cur_lineno),
                Instr("CALL_METHOD", 1, lineno=cur_lineno),
                Instr("LOAD_GLOBAL", func_name, lineno=cur_lineno),
                Instr("STORE_ATTR", "__code__", lineno=cur_lineno),

                Instr("LOAD_GLOBAL", func_name, lineno=cur_lineno)
            ])

            for i in range(argcount):
                patch_block.append(Instr("LOAD_FAST", arg[i], lineno=cur_lineno))

            if kwargscount > 0:
                for i in range(kwargscount):
                    patch_block.append(Instr("LOAD_FAST", kwargs[i], lineno=cur_lineno))
                patch_block.append(Instr("LOAD_CONST", kwargs, lineno=cur_lineno))
                patch_block.append(Instr("CALL_FUNCTION_KW", argcount + kwargscount, lineno=cur_lineno))
            else:
                patch_block.append(Instr("CALL_FUNCTION", argcount, lineno=cur_lineno))     
            patch_block.append(Instr('RETURN_VALUE', lineno=cur_lineno))

            patch_block.append(patch_not_exist_label)
            new_bc.extend(patch_block)

            except_block = []
            except_label = Label()
            repair_mode_label = Label()
            except_reraise_label = Label()

            # Entry try block
            new_bc.append(Instr('SETUP_FINALLY', except_label, lineno=cur_lineno))  # Declare try block
            
            for instr in bc:
                if (
                    isinstance(instr, Instr)
                    and instr.name == 'LOAD_CONST'
                    and isinstance(instr.arg, CodeType)
                    and '__axolotl__' not in instr.arg.co_consts
                    and not self.is_class_code(instr.arg)
                ):
                    # Instrument nested CodeType
                    new_bc.append(Instr('LOAD_CONST', self.insert_try_except(instr.arg), lineno=instr.lineno))
                elif isinstance(instr, Instr) and instr.name == 'RETURN_VALUE':
                    if any(isinstance(i, Instr) and i.name in {"SETUP_FINALLY", "SETUP_EXCEPT"} for i in new_bc):
                        new_bc.append(Instr('POP_BLOCK', lineno=cur_lineno))
                    new_bc.append(instr)
                else:
                    new_bc.append(instr)

            except_block.append(except_label)
            except_block.append(Instr('DUP_TOP', lineno=cur_lineno))
            except_block.append(Instr('LOAD_GLOBAL', 'Exception', lineno=cur_lineno))
            if PYTHON_VERSION[1] <= 8:
                except_block.append(Instr('COMPARE_OP', Compare.EXC_MATCH, lineno=cur_lineno))
                except_block.append(Instr('POP_JUMP_IF_FALSE', except_reraise_label, lineno=cur_lineno))
            else:
                except_block.append(
                    Instr('JUMP_IF_NOT_EXC_MATCH', except_reraise_label, lineno=cur_lineno)
                )

            except_block.append(Instr('POP_TOP', lineno=cur_lineno))
            except_block.append(Instr('STORE_FAST', '__ax_exc', lineno=cur_lineno))
            except_block.append(Instr('POP_TOP', lineno=cur_lineno))
            
            # mode = mc.mode_check()
            except_block.append(Instr('LOAD_FAST', '__ax_mc', lineno=cur_lineno))
            except_block.append(Instr('LOAD_METHOD', 'mode_check', lineno=cur_lineno))
            except_block.append(Instr('CALL_METHOD', 0, lineno=cur_lineno))
            except_block.append(Instr('STORE_FAST', '_ex_mode', lineno=cur_lineno))


            # safe_mode_label
            """
                print(f'Exception occur : {_sc_e}')
                print('Mode checking...')

                if mode == '0':
                    print('Mode is safe mode, change to repair mode')
                    mc.repair_mode()
                    print('First patch generate')
                    re.except_handler(_sc_e)           # repair에 validation파트 포함      
                    exit(1)  
            """

            except_block.append(Instr('LOAD_GLOBAL', 'print', lineno=cur_lineno))
            except_block.append(Instr('LOAD_CONST', 'Exception occur', lineno=cur_lineno))
            except_block.append(Instr('CALL_FUNCTION', 1, lineno=cur_lineno))
            except_block.append(Instr('POP_TOP', lineno=cur_lineno))

            except_block.append(Instr('LOAD_FAST', '_ex_mode', lineno=cur_lineno))
            except_block.append(Instr('LOAD_CONST', '0', lineno=cur_lineno))
            except_block.append(Instr('COMPARE_OP', Compare.EQ, lineno=cur_lineno))
            except_block.append(Instr('POP_JUMP_IF_FALSE', repair_mode_label, lineno=cur_lineno))

            except_block.append(Instr('LOAD_FAST', '__ax_mc', lineno=cur_lineno))
            except_block.append(Instr('LOAD_METHOD', 'repair_mode', lineno=cur_lineno))
            except_block.append(Instr('CALL_METHOD', 0, lineno=cur_lineno))
            except_block.append(Instr('POP_TOP', lineno=cur_lineno))

            except_block.append(Instr('LOAD_FAST', '__ax_re', lineno=cur_lineno))
            except_block.append(Instr('LOAD_METHOD', 'except_handler', lineno=cur_lineno))
            except_block.append(Instr('LOAD_FAST', '__ax_exc', lineno=cur_lineno))
            except_block.append(Instr('CALL_METHOD', 1, lineno=cur_lineno))
            except_block.append(Instr('POP_TOP', lineno=cur_lineno))

            # repair label
            """
                else if mode =='-1':
                    print('Mode is repair')
                    pass
            """
            except_block.append(repair_mode_label)
            except_block.append(Instr('LOAD_FAST', '_ex_mode', lineno=cur_lineno))
            except_block.append(Instr('LOAD_CONST', '-1', lineno=cur_lineno))
            except_block.append(Instr('COMPARE_OP', Compare.EQ, lineno=cur_lineno))
            except_block.append(Instr('POP_JUMP_IF_FALSE', except_reraise_label, lineno=cur_lineno))

            except_block.append(Instr('LOAD_GLOBAL', 'print', lineno=cur_lineno))
            except_block.append(Instr('LOAD_CONST', 'Mode is repair mode', lineno=cur_lineno))
            except_block.append(Instr('CALL_FUNCTION', 1, lineno=cur_lineno))
            except_block.append(Instr('POP_TOP', lineno=cur_lineno))

            # except reraise label
            except_block.append(except_reraise_label)
            if PYTHON_VERSION[1] <= 8:
                except_block.append(Instr('RAISE_VARARGS', 0, lineno=cur_lineno))
            else:
                except_block.append(Instr('RERAISE', 0, lineno=cur_lineno))            

            instrumented_bc = Bytecode(new_bc + except_block)
            instrumented_bc._copy_attr_from(bc)
   
        else:
            for instr in bc:
                if (
                    isinstance(instr, Instr)
                    and instr.name == 'LOAD_CONST'
                    and isinstance(instr.arg, CodeType)
                    and '__axolotl__' not in instr.arg.co_consts
                    and not self.is_class_code(instr.arg)
                ):
                    # Instrument nested CodeType
                    new_bc.append(Instr('LOAD_CONST', self.insert_try_except(instr.arg), lineno=instr.lineno))
                else:
                    new_bc.append(instr)
            instrumented_bc = Bytecode(new_bc)
            instrumented_bc._copy_attr_from(bc)

        try:
            new_code = instrumented_bc.to_code()
        except:
            print(code.co_filename)
            dump_bytecode(bc, lineno=True)
            print('------------------')
            dump_bytecode(instrumented_bc, lineno=True)
            raise
        
        return new_code
    
    def is_class_code(self, code_obj: CodeType) -> bool:
        bytecode = Bytecode.from_code(code_obj)
        instructions = list(bytecode)

        store_names = {instr.arg for instr in instructions if isinstance(instr, Instr) and instr.name == "STORE_NAME"}
        return {"__module__", "__qualname__"}.issubset(store_names)

    
    def insert_try_except_for_patchcode(self, code: CodeType):
        bc = Bytecode.from_code(code)
        cur_lineno = code.co_firstlineno

        is_global = code.co_name == '<module>' 

        # Skip if already instrumented
        if isinstance(bc[0], Instr) and bc[0].name == 'LOAD_CONST' and bc[0].arg == '__axolotl__':
            return code

        new_bc = [Instr('LOAD_CONST', '__axolotl__', lineno=1)]

        # import axolotl.mode as mc
        new_bc.append(Instr('LOAD_CONST', 0, lineno=cur_lineno))
        new_bc.append(Instr('LOAD_CONST', None, lineno=cur_lineno))
        new_bc.append(Instr('IMPORT_NAME', 'axolotl.mode', lineno=cur_lineno))
        new_bc.append(Instr('IMPORT_FROM', 'mode', lineno=cur_lineno))
        new_bc.append(Instr('STORE_FAST', '__ax_mc', lineno=cur_lineno))
        new_bc.append(Instr('POP_TOP', lineno=cur_lineno))

        # import axolotl.repair as re
        new_bc.append(Instr('LOAD_CONST', 0, lineno=cur_lineno))
        new_bc.append(Instr('LOAD_CONST', None, lineno=cur_lineno))
        new_bc.append(Instr('IMPORT_NAME', 'axolotl.repair', lineno=cur_lineno))
        new_bc.append(Instr('IMPORT_FROM', 'repair', lineno=cur_lineno))
        new_bc.append(Instr('STORE_FAST', '__ax_re', lineno=cur_lineno))
        new_bc.append(Instr('POP_TOP', lineno=cur_lineno))

        # import axolotl.patch as pc
        new_bc.append(Instr('LOAD_CONST', 0, lineno=cur_lineno))
        new_bc.append(Instr('LOAD_CONST', None, lineno=cur_lineno))
        new_bc.append(Instr('IMPORT_NAME', 'axolotl.patch', lineno=cur_lineno))
        new_bc.append(Instr('IMPORT_FROM', 'patch', lineno=cur_lineno))
        new_bc.append(Instr('STORE_FAST', '__ax_pc', lineno=cur_lineno))
        new_bc.append(Instr('POP_TOP', lineno=cur_lineno))


        ## 이 밑으로 try-except 블록
        except_block = []
        except_label = Label()
        repair_mode_label = Label()
        except_reraise_label = Label()

        # Entry try block
        new_bc.append(Instr('SETUP_FINALLY', except_label, lineno=cur_lineno))
        for instr in bc:
            if (
                isinstance(instr, Instr)
                and instr.name == 'LOAD_CONST'
                and isinstance(instr.arg, CodeType)
                and '__axolotl__' not in instr.arg.co_consts
                and not self.is_class_code(instr.arg)
            ):
                # Instrument nested CodeType
                new_bc.append(Instr('LOAD_CONST', self.insert_try_except(instr.arg), lineno=instr.lineno))
            elif isinstance(instr, Instr) and instr.name == 'RETURN_VALUE':
                if any(isinstance(i, Instr) and i.name in {"SETUP_FINALLY", "SETUP_EXCEPT"} for i in new_bc):
                    new_bc.append(Instr('POP_BLOCK', lineno=cur_lineno))

                new_bc.append(instr)
            else:
                new_bc.append(instr)

        except_block.append(except_label)
        except_block.append(Instr('DUP_TOP', lineno=cur_lineno))
        except_block.append(Instr('LOAD_GLOBAL', 'Exception', lineno=cur_lineno))
        if PYTHON_VERSION[1] <= 8:
            except_block.append(Instr('COMPARE_OP', Compare.EXC_MATCH, lineno=cur_lineno))
            except_block.append(Instr('POP_JUMP_IF_FALSE', except_reraise_label, lineno=cur_lineno))
        else:
            except_block.append(
                Instr('JUMP_IF_NOT_EXC_MATCH', except_reraise_label, lineno=cur_lineno)
            )

        except_block.append(Instr('POP_TOP', lineno=cur_lineno))
        except_block.append(Instr('STORE_FAST', '__ax_exc', lineno=cur_lineno))
        except_block.append(Instr('POP_TOP', lineno=cur_lineno))
        
        # mode = mc.mode_check()
        except_block.append(Instr('LOAD_FAST', '__ax_mc', lineno=cur_lineno))
        except_block.append(Instr('LOAD_METHOD', 'mode_check', lineno=cur_lineno))
        except_block.append(Instr('CALL_METHOD', 0, lineno=cur_lineno))
        except_block.append(Instr('STORE_FAST', 'mode', lineno=cur_lineno))

        # safe_mode_label
        """
            print(f'Exception occur : {_sc_e}')
            print('Mode checking...')

            if mode == '0':
                print('Mode is safe mode, change to repair mode')
                mc.repair_mode()
                print('First patch generate')
                re.except_handler(_sc_e)           # repair에 validation파트 포함      
                exit(1)  
        """
        except_block.append(Instr('LOAD_GLOBAL', 'print', lineno=cur_lineno))
        except_block.append(Instr('LOAD_CONST', 'Exception occur :', lineno=cur_lineno))
        except_block.append(Instr('LOAD_FAST', '__ax_exc', lineno=cur_lineno))
        except_block.append(Instr('FORMAT_VALUE', 0, lineno=cur_lineno))
        except_block.append(Instr('BUILD_STRING', 2, lineno=cur_lineno))
        except_block.append(Instr('CALL_FUNCTION', 1, lineno=cur_lineno))
        except_block.append(Instr('POP_TOP', lineno=cur_lineno))

        except_block.append(Instr('LOAD_GLOBAL', 'print', lineno=cur_lineno))
        except_block.append(Instr('LOAD_CONST', 'Mode checking', lineno=cur_lineno))
        except_block.append(Instr('CALL_FUNCTION', 1, lineno=cur_lineno))
        except_block.append(Instr('POP_TOP', lineno=cur_lineno))

        except_block.append(Instr('LOAD_FAST', 'mode', lineno=cur_lineno))
        except_block.append(Instr('LOAD_CONST', '0', lineno=cur_lineno))
        except_block.append(Instr('COMPARE_OP', Compare.EQ, lineno=cur_lineno))
        except_block.append(Instr('POP_JUMP_IF_FALSE', repair_mode_label, lineno=cur_lineno))

        except_block.append(Instr('LOAD_GLOBAL', 'print', lineno=cur_lineno))
        except_block.append(Instr('LOAD_CONST', 'Mode is safe mode, change to repair mode', lineno=cur_lineno))
        except_block.append(Instr('CALL_FUNCTION', 1, lineno=cur_lineno))
        except_block.append(Instr('POP_TOP', lineno=cur_lineno))

        except_block.append(Instr('LOAD_FAST', '__ax_mc', lineno=cur_lineno))
        except_block.append(Instr('LOAD_METHOD', 'repair_mode', lineno=cur_lineno))
        except_block.append(Instr('CALL_METHOD', 0, lineno=cur_lineno))
        except_block.append(Instr('POP_TOP', lineno=cur_lineno))

        except_block.append(Instr('LOAD_GLOBAL', 'print', lineno=cur_lineno))
        except_block.append(Instr('LOAD_CONST', 'First patch generate', lineno=cur_lineno))
        except_block.append(Instr('CALL_FUNCTION', 1, lineno=cur_lineno))
        except_block.append(Instr('POP_TOP', lineno=cur_lineno))

        except_block.append(Instr('LOAD_FAST', '__ax_re', lineno=cur_lineno))
        except_block.append(Instr('LOAD_METHOD', 'except_handler', lineno=cur_lineno))
        except_block.append(Instr('LOAD_FAST', '__ax_exc', lineno=cur_lineno))
        except_block.append(Instr('CALL_METHOD', 1, lineno=cur_lineno))
        except_block.append(Instr('POP_TOP', lineno=cur_lineno))

        # except_block.append(Instr('LOAD_GLOBAL', 'exit', lineno=cur_lineno))
        # except_block.append(Instr('LOAD_CONST', 1, lineno=cur_lineno))
        # except_block.append(Instr('CALL_FUNCTION', 1, lineno=cur_lineno))
        # except_block.append(Instr('POP_TOP', lineno=cur_lineno))

        # repair label
        """
            else if mode =='-1':
                print('Mode is repair')
                pass
        """
        except_block.append(repair_mode_label)
        except_block.append(Instr('LOAD_FAST', 'mode', lineno=cur_lineno))
        except_block.append(Instr('LOAD_CONST', '-1', lineno=cur_lineno))
        except_block.append(Instr('COMPARE_OP', Compare.EQ, lineno=cur_lineno))
        except_block.append(Instr('POP_JUMP_IF_FALSE', except_reraise_label, lineno=cur_lineno))

        except_block.append(Instr('LOAD_GLOBAL', 'print', lineno=cur_lineno))
        except_block.append(Instr('LOAD_CONST', 'Mode is repair mode', lineno=cur_lineno))
        except_block.append(Instr('CALL_FUNCTION', 1, lineno=cur_lineno))
        except_block.append(Instr('POP_TOP', lineno=cur_lineno))

        # # validation label
        # except_block.append(val_mode_label)
        # except_block.append(Instr('LOAD_FAST', 'mode', lineno=cur_lineno))
        # except_block.append(Instr('LOAD_CONST', 'validation', lineno=cur_lineno))
        # except_block.append(Instr('COMPARE_OP', Compare.EQ, lineno=cur_lineno))
        # except_block.append(Instr('POP_JUMP_IF_FALSE', except_reraise_label, lineno=cur_lineno))

        # except_block.append(Instr('LOAD_GLOBAL', 'print', lineno=cur_lineno))
        # except_block.append(Instr('LOAD_CONST', 'Mode is validation', lineno=cur_lineno))
        # except_block.append(Instr('CALL_FUNCTION', 1, lineno=cur_lineno))
        # except_block.append(Instr('POP_TOP', lineno=cur_lineno))

        # except reraise label
        except_block.append(except_reraise_label)
        # except_block.append(Instr('POP_EXCEPT', lineno=cur_lineno)) ### 3.7 여기 수정함
        if PYTHON_VERSION[1] <= 8:
            except_block.append(Instr('RAISE_VARARGS', 0, lineno=cur_lineno))
        else:
            except_block.append(Instr('RERAISE', 0, lineno=cur_lineno))

        instrumented_bc = Bytecode(new_bc + except_block)
        instrumented_bc._copy_attr_from(bc)
        
        try:
            new_code = instrumented_bc.to_code()
            #print(new_code.co_varnames)
        except:
            print(code.co_filename)
            dump_bytecode(bc, lineno=True)
            print('------------------')
            dump_bytecode(instrumented_bc, lineno=True)
            raise
        
        return new_code