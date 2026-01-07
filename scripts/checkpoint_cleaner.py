import os
import shutil
import sys

def clean_directory(target_path):
    if os.path.exists(target_path):
        try:
            if os.path.isdir(target_path):
                shutil.rmtree(target_path)
            else:
                os.remove(target_path)
            print(f"[Success] Deleted: {target_path}")
        except PermissionError:
            print(f"[Permission Error] Please run with 'sudo'. Cannot delete: {target_path}")
        except Exception as e:
            print(f"[Error] Failed to delete {target_path}: {e}")
    else:
        print(f"[Skip] Not found: {target_path}")

if __name__ == "__main__":
    targets = sys.argv[1:]
    if targets:
        for target in targets:
            clean_directory(target)
    else:
        print("Usage: python3 cleaner.py <path1> <path2> ...")

    