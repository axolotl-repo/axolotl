import subprocess
import shutil
import os
import time
import psutil

import axolotl.mode as mc
from .validation import Validater
from .logger import get_logger, get_reporter

class Checkpoint:
    def __init__(self, wdir):
        self.checkpoint_num=0
        self.restore_occur=False
        self.restore_num=0
        self.main_pid = os.getpid()
        self.validate_checkpoint_num = 0
        self.val = Validater()
        self.val_part1 = False
        self.val_part2_count = 0
        self.mutate_num = 0
        self.wdir = wdir

        self.val_failed = False

        self.logger = get_logger()
        self.reporter = get_reporter()

    def store_checkpoint(self, proc:psutil.Process, file_path:str):
        if self.restore_occur == True:
             self.checkpoint_num = 0
             self.restore_occur = False
        
        if self.checkpoint_num == 0:
            shutil.rmtree(file_path, ignore_errors=True)
            os.makedirs(file_path, exist_ok=True)

        os.makedirs(f'{file_path}/{self.checkpoint_num}', exist_ok=True)

        cmd = ['criu', 'dump','--tree',str(proc.pid),
               '--images-dir',f'{file_path}/{self.checkpoint_num}',
               '--leave-running', '--track-mem','--shell-job','-v1','--tcp-established']

        cmd.append('--external')
        cmd.append(f'/proc/{self.main_pid}/ns/time')

        if self.checkpoint_num != 0:
            cmd.append('--prev-images-dir')
            cmd.append(f'../{self.checkpoint_num-1}')

        self.logger.info(f'[CRIU] Checkpointing {self.checkpoint_num} checkpoint for process {proc.pid}...')
        res=subprocess.run(cmd)
        if res.returncode != 0:
            self.logger.error(f'[CRIU] Checkpoint error: {res.stdout.decode()}')
            proc.kill()
            exit(1)
        
        self.logger.info(f'[CRIU] Checkpoint {self.checkpoint_num} for process {proc.pid} stored successfully.')
        self.checkpoint_num+=1


    def restore_checkpoint(self, file_path:str):        
        cmd=['criu','restore','-v1','--shell-job','-D',f'{file_path}',
             '--tcp-established'
            ]

        cmd.append('-J')
        cmd.append(f'time:/proc/{self.main_pid}/ns/time')

        self.logger.info(f'[CRIU] Restoring checkpoint {self.validate_checkpoint_num}...')

        proc = subprocess.Popen(cmd)
        if mc.mode_check() == '0':
            time.sleep(1.0)

        self.logger.info('[CRIU] Restore Success, Program Continue\n')

        restored_pid = None
        for child in psutil.Process(proc.pid).children():
            restored_pid = child.pid
            break

        if restored_pid is None:
            self.criu_loop(psutil.Process(proc.pid))
        else:
            self.criu_loop(psutil.Process(restored_pid))



# validation_mode(1)
# validation_fail_mode(2) 
# safe mode(0)
# repair mode(-1)
    def criu_loop(self, proc:psutil.Process):
        # crash_recorded = False
        while True:
            try:
                state = proc.is_running()
            except:
                pass
        
            mode = mc.mode_check()

            if mode == '2':      # validation fail 
                try:
                    proc.kill()
                except:
                    pass

                self.val_failed = True

                msg = f'Validation Failed (Mode 2 detected).'
                if self.val_part1:
                    msg += f' (Failed in Part 2 after {self.val_part2_count} retries)'
                else:
                    msg += ' (Failed in Part 1 or Crash)'
                
                self.logger.warning(msg)
                
                # [Reporter]
                if self.reporter:
                    self.reporter.set_result("status", "validation_failed")
                    self.reporter.save_report()

                self.logger.info('Test Done')
                break

            elif mode == '1': 
                if proc:
                    proc.wait()
                self.val_part1 = True
                self.validate_checkpoint_num = self.checkpoint_num-1
                # self.validate_checkpoint_num += 1

                self.logger.info(f'Validation complete! Returning to safe mode')
                mc.safe_mode()
                if self.reporter:
                    # self.reporter.end_validation_timer(part=2)
                    self.reporter.set_result("status", "success")
                    self.reporter.start_after_validate_timer()
                    self.reporter.save_report()

                self.restore_checkpoint(f'{self.wdir}/checkpoints{self.restore_num}/{self.validate_checkpoint_num}')
                # self.restore_checkpoint(f'{self.wdir}/checkpoints{self.restore_num}/{self.checkpoint_num-1}') 
                break

            # reapir mode(-1)                
            elif mode == '-1':
                time.sleep(1.)
                continue

            # safe mode(0)
            elif mode == '0':
                try:
                    state = proc.status()
                    if state in ('running', 'sleeping', 'disk-sleep', 'tracing-stop'):
                        self.store_checkpoint(proc,f'{self.wdir}/checkpoints{self.restore_num}')
                    else:
                        self.logger.debug(f'Process terminated. State: {state}')
                        if self.reporter:
                            self.reporter.end_after_validate_timer()
                            self.reporter.save_report()
                        break
                except (psutil.NoSuchProcess, psutil.ZombieProcess):
                    self.logger.info("Process finished (NoSuchProcess).")
                    if self.reporter:
                        self.reporter.end_after_validate_timer()
                        self.reporter.save_report()
                    break
                except:
                    self.logger.debug('subprocess state is NONE -> passing')
                    pass
            else:
                time.sleep(1.)
                continue

            time.sleep(1.0)
        
        self.logger.info("CRIU Loop Finished")
        try:
            proc.kill()
        except:
            pass

