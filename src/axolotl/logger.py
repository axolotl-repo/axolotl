import logging
import os
import json
import time

from contextlib import contextmanager
from typing import Dict, Any, List, Optional

# global instances
_logger = None
_reporter = None

class AxolotlReporter:
    def __init__(self, log_dir: str, args: Dict[str, Any]):
        self.log_file = os.path.join(log_dir, "time_profile.json")
        self.sync_file = os.path.join(log_dir, "reporter_sync.json")
        
        if args:
            current_time = time.time()
            self.data = {
                "meta": {
                    "args": str(args),
                    "start_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "start_timestamp": current_time,
                    "end_time": None,
                    "status": "running",
                    "validation_iter": 0,
                },
                "timings": {
                    "total_duration": 0.0,            
                    "time_to_first_fail": 0.0,        
                    "total_patch_generation_time": 0.0, 
                    "total_validation_time": 0.0,     
                    "after_validate": 0.0             
                },
                "patch_generation_time": {
                    "first_patch_generate_time": 0.0,
                    "validation_feedback_iter": []
                },
                "patch_validation_time": {
                    "iter": [],
                },
                "stats": {
                    "status": "running",       
                    "validation_iter": 0
                }
            }
            self._start_timestamp = current_time
            self._save_sync()
        else:
            self._load_sync()
            if not hasattr(self, 'data'):
                self.data = {}
                self._start_timestamp = time.time()
            else:
                meta = self.data.get("meta", {})
                if "start_timestamp" in meta:
                    self._start_timestamp = meta["start_timestamp"]

        self._temp_timers = {}

    def _save_sync(self):
        try:
            with open(self.sync_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            if _logger: _logger.error(f"Sync save failed: {e}")

    def _load_sync(self):
        if os.path.exists(self.sync_file):
            try:
                with open(self.sync_file, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
            except Exception as e:
                pass

    def _update_totals(self):
        if "patch_generation_time" not in self.data: return

        pg = self.data["patch_generation_time"]
        pv = self.data["patch_validation_time"]
        tm = self.data["timings"]

        first = pg["first_patch_generate_time"] or 0.0
        feedback_sum = sum(pg["validation_feedback_iter"])
        tm["total_patch_generation_time"] = first + feedback_sum

        val_sum = sum(pv["iter"])
        tm["total_validation_time"] = val_sum

        tm["total_duration"] = (
            (tm["time_to_first_fail"] or 0.0) +
            tm["total_patch_generation_time"] +
            tm["total_validation_time"] +
            tm["after_validate"]
        )

        st = self.data["stats"]
        mt = self.data["meta"]
        
        mt["status"] = st.get("status", "running")
        mt["validation_iter"] = st.get("validation_iter", 0)

    def record_crash_time(self):
        self._load_sync()
        if self.data["timings"]["time_to_first_fail"] == 0.0:
            duration = time.time() - self._start_timestamp
            self.data["timings"]["time_to_first_fail"] = duration
            self._save_sync()

    @contextmanager
    def measure_patch_gen(self, mode: str = 'feedback'):
        """
        mode: 'first' (초기 생성) 또는 그 외 (피드백 루프)
        """
        start = time.time()
        yield
        duration = time.time() - start
        
        self._load_sync()
        if mode == 'first':
            self.data["patch_generation_time"]["first_patch_generate_time"] = duration
        else:
            self.data["patch_generation_time"]["validation_feedback_iter"].append(duration)
        self._save_sync()

    @contextmanager
    def measure_validation(self):
        start = time.time()
        yield
        duration = time.time() - start
        self._record_validation_time(duration)

    def start_validation_timer(self):
        self._temp_timers['validation'] = time.time()

    def end_validation_timer(self):
        key = 'validation'
        if key in self._temp_timers:
            duration = time.time() - self._temp_timers[key]
            self._record_validation_time(duration)
            del self._temp_timers[key]

    def _record_validation_time(self, duration: float):
        self._load_sync()
        self.data["patch_validation_time"]["iter"].append(duration)
        self.data["stats"]["validation_iter"] += 1 
        self._save_sync()

    def start_after_validate_timer(self):
        self._temp_timers['after_validate'] = time.time()

    def end_after_validate_timer(self):
        if 'after_validate' in self._temp_timers:
            duration = time.time() - self._temp_timers['after_validate']
            self._load_sync()
            self.data["timings"]["after_validate"] = duration
            self._save_sync()
            del self._temp_timers['after_validate']

    def set_result(self, key, value):
        self._load_sync()
        self.data["stats"][key] = value
        self._save_sync()

    def increment_stat(self, key):
        self._load_sync()
        if key not in self.data["stats"]:
            self.data["stats"][key] = 0
        self.data["stats"][key] += 1
        self._save_sync()

    def save_report(self):
        self._load_sync()
        self.data["meta"]["end_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self._update_totals() 
        
        try:
            with open(self.log_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
        except Exception:
            pass

def setup_logger(wdir: str, args=None):
    global _logger, _reporter
    log_dir = os.path.join(wdir, 'log')
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "axolotl_debug.log")

    logger = logging.getLogger("axolotl")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    if logger.handlers: logger.handlers.clear()
    
    formatter = logging.Formatter('[%(asctime)s] %(message)s', datefmt='%H:%M:%S')
    fh = logging.FileHandler(log_path, mode='a', encoding='utf-8')
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    _logger = logger
    _reporter = AxolotlReporter(log_dir, args)
    
    return logger

def get_logger(name="axolotl"):
    if _logger: return _logger
    return logging.getLogger("axolotl")
    
def get_reporter() -> Optional[AxolotlReporter]:
    return _reporter