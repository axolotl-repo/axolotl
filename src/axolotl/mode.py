import os

def safe_mode():
    with open(f'{os.getenv("WDIR")}/process_mode', 'w') as f:
        f.write('0')

def repair_mode():
    with open(f'{os.getenv("WDIR")}/process_mode', 'w') as f:
        f.write('-1')

def validation_mode():
    with open(f'{os.getenv("WDIR")}/process_mode', 'w') as f:
        f.write('1')

def validation_fail_mode():
    with open(f'{os.getenv("WDIR")}/process_mode', 'w') as f:
        f.write('2')

def mode_check():
    with open(f'{os.getenv("WDIR")}/process_mode', 'r') as f:
        return f.read().strip()