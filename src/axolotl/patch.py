import os
import marshal

PATCH_FOLDER = f"{os.getenv('WDIR')}/patch_file"  # file_path

def func_patch_exist(func_name):
    if os.path.exists(os.path.join(PATCH_FOLDER, f"{func_name}_patch")):
        return True
    else:
        return False

def patched_func(func_name):
    with open(os.path.join(PATCH_FOLDER, f"{func_name}_patch"), "rb") as f:
        code_object = marshal.load(f)
    return code_object