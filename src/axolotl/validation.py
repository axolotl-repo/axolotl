import marshal
import inspect
import types
from types import FunctionType
import traceback
import os
import json
from pathlib import Path
from types import FunctionType

import random
import struct
import re
from unittest.mock import MagicMock  
from typing import Any, Dict, List, Tuple
from enum import Enum
import time

from .logger import get_logger, get_reporter

BRANCH_PATH = f"{os.getenv('WDIR')}/mutation"
PATCH_FOLDER = f"{os.getenv('WDIR')}/patch_file"

class Validater:
    def __init__(self, wdir: str = None):
        self.wdir = wdir or os.getenv("WDIR")
        self.logger = get_logger()
        self.reporter = get_reporter()

        self.max_mutations = 5
        # for quick test / we use 600 sec in paper
        # TODO : make duration as configurable parameter
        self.max_mutation_duration = 60 # seconds
        
        self.branch_path = os.path.join(self.wdir, 'mutation')
        self.patch_folder = os.path.join(self.wdir, 'patch_file')
        self.validation_exception = ''

    # validation part 1
    def validate_patch(self, patch_file_path, func_name, args, kwargs, globals_vars):
        """
        Validate a patch using the saved bytecode file.
        
        :param patch_file_path: Path to the file containing the patched bytecode.
        :param func_name: Name of the patched function.
        :param args: Positional arguments of the original function call.
        :param kwargs: Keyword arguments of the original function call.
        :param globals_vars: Global variables from the original function scope.
        :return: True if the patch is valid, False otherwise.
        """
        self.logger.info(f"[Val-1] Validating patch for '{func_name}'...")

        try:
            with open(patch_file_path, 'rb') as patch_file:
                patched_code = marshal.load(patch_file)
            patched_func = FunctionType(patched_code, globals_vars, func_name)
            sig = inspect.signature(patched_func)
            args_list = [args[key] for key in sig.parameters if key in args]
            valid_kwargs = {k: v for k, v in kwargs.items() if k not in sig.parameters}
            self.logger.debug(f"Input Args: {list(args.keys())}")
            result = patched_func(*args_list, **valid_kwargs)
            if isinstance(result, types.GeneratorType):
                for _ in result: pass 
            self.logger.info(f"[Val-1] Passed. Result type: {type(result).__name__}")
            return True
        except Exception as e:
            self.validation_exception = str(e)
            self.logger.warning(f"[Val-1] Failed: {e}")
            tb = traceback.format_exc()
            self.logger.debug(f"Traceback:\n{tb}")
            return False
    
    def regression_test(self, func_name, origin_code, patch_code, args, kwargs, globals_vars):
        start_time = time.time()
        mutator = Mutator()

        interesting_inputs = [] 

        self.logger.info(f"[Val-2] Starting Regression Test for {self.max_mutation_duration}s ...")

        while time.time() - start_time < self.max_mutation_duration:

            # 1. Input mutation
            mutated_args, mutated_kwargs = mutator.mutate_inputs(args, kwargs)

            # 2. Run buggy function with mutated input
            # - if pass -> interesting input
            # - if fail -> keep mutating
            try:
                origin_result = self.input_test(origin_code, func_name, mutated_args, mutated_kwargs, globals_vars)
            except Exception:
                # If Exception occur, continue mutating (mutation 기록할까? -> mutator에서 어차피 만든 muated input 저장함)
                continue

            # If no exception, run patched function with same mutated input -> interesting input에 기록하자
            interesting_inputs.append((mutated_args, mutated_kwargs))

            try:
                patch_result = self.input_test(patch_code, func_name, mutated_args, mutated_kwargs, globals_vars)
            except Exception as e:
                # 4. If patched function fail -> validation part2 fail
                if len(interesting_inputs) > 0:
                    self.logger.info(f"[Val-2] Saving {len(interesting_inputs)} interesting inputs ...")
                    mutator.save_interesting_input(interesting_inputs)
                else:
                    self.logger.info(f"[Val-2] No interesting input found during mutation.")
                self.logger.info(f"[Val-2] Regression Test Failed with {mutator.input_count} mutated input. Exception: {e}")

                return False
            
            # if origin_result != patch_result:
            #     self.logger.error(f"[Val-2] Logic Error Detected! Results differ. Origin: {origin_result}, Patch: {patch_result}")
            #     self._save_and_fail(mutator, interesting_inputs)
            #     return False

        if len(interesting_inputs) > 0:
            self.logger.info(f"[Val-2] Saving {len(interesting_inputs)} interesting inputs ...")
            mutator.save_interesting_input(interesting_inputs)
        else:
            self.logger.info(f"[Val-2] No interesting input found during mutation.")
        self.logger.info(f"[Val-2] Regression Test Passed for all {mutator.input_count} mutated inputs within duration.(or no interesting input found)")
        return True
    
    def input_test(self, bytecode, func_name, args, kwargs, globals_vars):
        # 1. Function Reconstruction
        test_func = FunctionType(bytecode, globals_vars, func_name)
        
        # 2. Argument Mapping
        sig = inspect.signature(test_func)
        args_list = [args[key] for key in sig.parameters if key in args]
        valid_kwargs = {k: v for k, v in kwargs.items() if k not in sig.parameters}

        # 3. Execution
        result = test_func(*args_list, **valid_kwargs)

        # handling generator
        if isinstance(result, types.GeneratorType):
            for _ in result: pass       

        return result     

class Mutator:
    def __init__(self):
        self.wdir = os.getenv("WDIR")
        self.save_file_path = os.path.join(self.wdir, 'mutation', 'mutated_input_')
        self.logger = get_logger()
        self.input_count = 0

        self.mutated_input_log = os.path.join(self.wdir, 'mutation', 'mutated_inputs.json')
        self.interesting_input_log = os.path.join(self.wdir, 'mutation', 'interesting_inputs.json')

    def mutate_inputs(self, args: Dict[str, Any], kwargs: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        # 1~10 random mutations for each argument
        mutated_args = {k: self.mutate_random_count(v) for k, v in args.items()}
        mutated_kwargs = {k: self.mutate_random_count(v) for k, v in kwargs.items()}
        self.input_count += 1

        if self.input_count % 1000000 == 0:
            self.logger.debug(f"Generated {self.input_count} mutated inputs.")

        return mutated_args, mutated_kwargs
    
    def mutate_random_count(self, val):
        n = random.randint(1, 10)
        mutated_val = val
        for _ in range(n):
            mutated_val = self.mutate_object(mutated_val)
        return mutated_val
    
    def save_interesting_input(self, interesting_inputs: List[Tuple[Dict[str, Any], Dict[str, Any]]]) -> None:
        with open(self.interesting_input_log, 'a', encoding='utf-8') as f:
            for index, (mutated_args, mutated_kwargs) in enumerate(interesting_inputs):
                mutated_result = {
                    "index": index,
                    "args": mutated_args, 
                    "kwargs": mutated_kwargs
                }

                try:
                    f.write(json.dumps(mutated_result, default=str, ensure_ascii=False) + "\n")
                except Exception as e:
                    f.write(f'{{"error": "log_failed", "index": {index}, "reason": "{str(e)}"}}\n')
            
    def mutate_object(self, obj: object) -> object:
        random.seed(time.time())
        if isinstance(obj, Enum):
            return random.choice(list(obj.__class__))
        elif isinstance(obj, bool): # bool mutate
            return not obj
        elif isinstance(obj, int):  # int형 mutate
            return self.mutate_int(obj)
        elif isinstance(obj, float): # float형 mutate
            return self.mutate_float(obj)
        elif isinstance(obj, str):   # 문자열 mutate
            return self.mutate_string(obj)
        elif isinstance(obj, bytes): # 바이트 mutate
            return self.mutate_bytes(obj)
        elif isinstance(obj, Path):
            return self.mutate_path(obj)  # 파일 경로를 문자열로 변환 후 변이
        elif isinstance(obj, re.Pattern):
            return self.mutate_regex(obj)  # 정규식 변이
        elif isinstance(obj, MagicMock):
            return self.mutate_mock(obj)
        elif hasattr(obj, '__dict__'):
            fields = list(obj.__dict__.keys())
            if fields:
                field_to_mutate = random.choice(fields)
                new_value = self.mutate_object(getattr(obj, field_to_mutate))
                setattr(obj, field_to_mutate, new_value)
            return obj
        return obj

    def mutate_int(self, value: int) -> int:
        mutation_type = random.choice([
            "bit_flip", "arithmetic", "interesting_values"
        ])

        if mutation_type == "bit_flip":
            bit = random.randint(0, 31)
            return value ^ (1 << bit)

        elif mutation_type == "arithmetic":
            delta = random.randint(-35, 35)
            return value + delta

        elif mutation_type == "interesting_values":
            interesting_values = [0, -1, 1, 255, 256, 4096, -128, 32767]
            return random.choice(interesting_values)

        return value

    def mutate_float(self, value: float) -> float:
        binary = struct.pack('d', value)
        index = random.randint(0, 63)
        bytewise = index // 8
        bitwise = index % 8
        new_binary = (
            binary[:bytewise]
            + bytes([binary[bytewise] ^ (1 << bitwise)])
            + binary[bytewise + 1:]
        )
        return struct.unpack('d', new_binary)[0]

    def mutate_string(self, value: str) -> str:
        value = list(value)

        if random.random() < 0.3:
            # Insert a random character
            index = random.randint(0, len(value))
            value.insert(index, chr(random.randint(32, 126)))

        if random.random() < 0.3:
            # Delete a random character
            if value:
                index = random.randint(0, len(value) - 1)
                value.pop(index)

        if random.random() < 0.3:
            # Flip a random bit in a character
            if value:
                index = random.randint(0, len(value) - 1)
                char = value[index]
                bit = random.randint(0, 7)
                value[index] = chr(ord(char) ^ (1 << bit))

        return ''.join(value)

    def mutate_bytes(self, value: bytes) -> bytes:
        value = bytearray(value)

        # byte insertion
        if random.random() < 0.3:
            index = random.randint(0, len(value))
            value.insert(index, random.randint(0, 255))

        # byte deletion
        if random.random() < 0.3 and len(value) > 0:
            index = random.randint(0, len(value) - 1)
            del value[index]

        # single bit flip
        if random.random() < 0.3 and len(value) > 0:
            index = random.randint(0, len(value) - 1)
            bit = random.randint(0, 7)
            value[index] ^= (1 << bit)

        # block copy
        if random.random() < 0.3 and len(value) > 1:
            start = random.randint(0, len(value) - 1)
            size = random.randint(1, min(4, len(value) - start))
            block = value[start:start + size]
            insert_at = random.randint(0, len(value))
            value[insert_at:insert_at] = block

        # block deletion
        if random.random() < 0.3 and len(value) > 1:
            start = random.randint(0, len(value) - 1)
            size = random.randint(1, min(4, len(value) - start))
            del value[start:start + size]

        return bytes(value)

    def mutate_path(self, value: Path) -> str:
        parts = value.parts
        mutated_parts = list(parts)
        if len(mutated_parts) > 1:
            index = random.randint(1, len(mutated_parts) - 1)
            mutated_parts[index] = self.mutate_string(mutated_parts[index])
        return '/'.join(mutated_parts)

    def mutate_regex(self, pattern: re.Pattern) -> re.Pattern:
        original_pattern = pattern.pattern
        mutated_pattern = self.mutate_string(original_pattern)

        try:
            return re.compile(mutated_pattern)
        except re.error:
            return pattern
        
    def mutate_mock(self, mock: MagicMock) -> MagicMock:
        new_call_count = random.randint(0, 100)
        for _ in range(new_call_count):
            mock()

        mock.called = random.choice([True, False])
        new_call_args_list = []
        for _ in range(random.randint(0, 5)):
            args = tuple(self.mutate_object(random.randint(0, 10)) for _ in range(random.randint(1, 3)))
            kwargs = {f"key{i}": self.mutate_object(random.randint(0, 10)) for i in range(random.randint(0, 2))}
            new_call_args_list.append((args, kwargs))
        mock._mock_call_args_list = new_call_args_list

        return mock
    
    # def _has_magicmock(self, container):
    #     return any(isinstance(v, MagicMock) for v in container.values())
    
    # def serialize_magicmock(self, obj):
    #     if isinstance(obj, MagicMock):
    #         return {
    #             "type": "MagicMock",
    #             "id": id(obj),
    #             "call_count": obj.call_count,
    #             "called": obj.called,
    #             "call_args_list": [str(call) for call in obj.call_args_list]
    #         }
    #     return obj
    
    # def handle_magicmock(self, data: Dict[str, Any]) -> Dict[str, Any]:
    #     serialized_args = [self.serialize_magicmock(arg) if isinstance(arg, MagicMock) else arg for arg in data["args"]]
    #     serialized_kwargs = {k: self.serialize_magicmock(v) if isinstance(v, MagicMock) else v for k, v in data["kwargs"].items()}
    #     return {"args": serialized_args, "kwargs": serialized_kwargs}

# =========================================================
# Helper functions
# =========================================================
# def save_branch_path(func_name, branch_id):
#     """
#     Instrumentation된 코드가 직접 호출하는 함수 (Global Scope 유지 필요)
#     """
#     mutate_count = get_mutate_count()
#     branch_dir = BRANCH_PATH
    
#     # Mode에 따라 저장 위치 결정
#     # Mode 3: Origin Validation -> origin_result
#     # Mode 4: Patch Validation  -> patch_result
#     mode = mc.mode_check()
    
    # if mode == '3':
    #     path = os.path.join(branch_dir, "origin_result", f"{func_name}_{mutate_count}.txt")
    # else:
    #     path = os.path.join(branch_dir, "patch_result", f"{func_name}_{mutate_count}.txt")

    # try:
    #     with open(path, 'a') as f:
    #         f.write(f"{branch_id}\n")
    # except Exception:
    #     pass

# def update_mutate_count():
#     try:
#         with open(f'{os.getenv("WDIR")}/mutation/mutation_count', 'r') as f:
#             count = int(f.read().strip())
#             count += 1
#         with open(f'{os.getenv("WDIR")}/mutation/mutation_count', 'w') as f:
#             f.write(str(count))
#     except Exception as e:
#         print(f"Error occurred: {e}")

# def initilaize_mutate_count():
#     with open(f'{os.getenv("WDIR")}/mutation/mutation_count', 'w') as f:
#         f.write('0')

# def get_mutated_input(mutate_count):
#     file_path = f"{os.getenv('WDIR')}/mutation/mutated_input_{mutate_count}.pkl"
#     if not os.path.exists(file_path):
#         raise FileNotFoundError(f"Mutation file not found: {file_path}")

#     with open(file_path, "rb") as f:
#         data = pickle.load(f)  # data는 {'args': [...], 'kwargs': {...}} 형태의 딕셔너리
#         args = data['args']
#         kwargs = data['kwargs']

#     return args, kwargs

# def get_mutated_input(mutate_count):
#     path = os.path.join(os.getenv("WDIR"), 'mutation', f'mutated_input_{mutate_count}.pkl')
#     with open(path, "rb") as f:
#         data = pickle.load(f)
#     return data['args'], data['kwargs']

# def get_mutate_count():
#     with open(f'{os.getenv("WDIR")}/mutation/mutation_count', 'r') as f:
#         count = f.read().strip()
#     return count
