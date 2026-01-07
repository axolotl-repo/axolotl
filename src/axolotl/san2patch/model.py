import os
import shutil
from typing import Any, Dict, List, Tuple
import json
import requests
import re
# import numpy as np

# .core -> prompt
from .core import *
from axolotl.logger import get_logger, get_reporter

## 원래 san2patch에서, selection에서 sampling사용
# where-to-fix 에서는 / location 5개 생성후  -> scoring -> 3개 select(greedy or sampling)
# how-to-fix 에서는   / fix strategy(location당) 3개 생성 -> scoring -> 1개 select (greedy or sampling)
#
#  5 fault localization -> scoring/pruning -> 3 fault localization
#    -> 3 fix strategy(for each location) -> scoring/pruning -> 1 fix strategy(for each location)
#  => 3 location, 1 strategy each location
#  -> 3 patch for each strategy  => 9 patch candidates

## in Axolotl, (3->1, 3->1 방식으로하자 -> 함수단위니까) / 일단 간단하게greedy로 구현해놓고, 나중에 sampling 추가하는걸로
# 3 fault localization -> scoring -> 1개 select 
#  -> 3 fix strategy(for each location) -> scoring -> 1개 select (greedy or sampling)
#   -> l patch loc, suggestion -> 3 patch candidates
#   => test each patch candidate with sorted order(suggestion score)
#   -> 3개 다 실패시, feedback(각 패치 diff 전달) -> suggesstion 부터 다시 시도 (총 feedback 3번)
#   -> 총 9번의 패치 시도, (한가지 걸리는점, location이 1개이고 feedback 적용안돼서, 계속 다른 위치 잡을 수도 -> 나중에 location도 feedback추가?)

## 옵션처리 해야될거
## Base, ablation 1,2,3 -> 같은 run 부르더라도, ablation에 따라 다르게 패치생성하도록

class BaseModel:
    def __init__(self, project_path: str, project_name: str, max_trial:int=3):
        self.project_path = project_path
        self.project_name = project_name
        self.output_dir = ''
        self.max_trial = max_trial
        self.fl_branch_num = 3 # fault_localize 후보군 수
        self.fl_select_num = 1 # fault_localize 선택 수(after scoring/pruning)
        self.sr_branch_num = 3 # suggest_repair 후보군 수 (for each location)
        self.sr_select_num = 1 # suggest_repair 선택 수(after scoring/pruning, for each location)

        self.logger = get_logger()
        self.reporter = get_reporter()

        ## exception info(input) -> 나중에 인자로뺴야하나?
        self.exception_msg = ''
        self.exception_trace = ''
        self.target_line = ''
        self.buggy_code = ''
        
        ## for feedback
        # 이전에 실패한 patch diff 받아서 사용가능
        self.feedback_trial = 0
        self.prev_failed_patches: List[str] = []

        # result of comprehension -> root cause 분석 결과
        self.root_cause_aggregate = dict()
        self.root_causes_comprehend = []

        # result of fault localization -> sorted key: location, value: (score, rationale)
        self.fault_localization = []

        # result of suggest repair -> list of strategies
        self.final_strategies = []

        # result of patch generation -> list of patches
        self.patches = []


    def request(self, prompt: str) -> str:
        message = {
            'system_msg': SYSTEM_MESSAGE,
            'prompt' : prompt
        }
        r = requests.post('http://127.0.0.1:5000/request', json=message)
        res = r.json()['response']
        clean_response = re.sub(r'^```(?:json)?\s*|\s*```$', '', res.strip(), flags=re.MULTILINE)

        return clean_response

    # -> exception msg, trace, target buugy function 정보 기반, root cause 분석하도록
    def comprehend(self) -> Tuple[dict, dict, list]:
        # axolotl-1 : exception log 기반 root cause 분석
        self.logger.debug("[San2Patch] Finding root cause ...")
        root_cause_results = []

        for i in range(self.max_trial):
            msg = COMPREHEND_MESSAGE.replace('<stack_trace>', self.exception_trace).\
                            replace('<exception_log>', self.exception_msg).replace('<buggy_code>', self.buggy_code)
            
            while True:
                try:
                    res = self.request(msg)
                    comprehend_response = json.loads(res)
                except json.JSONDecodeError:
                    self.logger.debug("[San2Patch] JSON decode error in comprehend response, retrying...")
                    self.logger.debug("[San2Patch] response: " + res)
                    continue
                break
            # save interaction
            self.save_with_json(msg, json.dumps(comprehend_response), f'comprehend_{i}')
            
            # 여기서 max_trial만큼 description, rationale 모음
            exc_desc = comprehend_response['exception_description']
            exc_rationale = comprehend_response['rationale']
            root_cause_results.append((msg, comprehend_response, exc_desc, exc_rationale))

        # axolotl-2 : root cause aggregation
        # Aggregate results
        self.logger.debug("[San2Patch] Aggregating comprehension results and getting final results...")
        exc_desc = ''
        exc_rationale = ''
        for i in range(self.max_trial):
            exc_desc += f'{i}. ' + root_cause_results[i][2] + '\n'
            exc_rationale += f'{i}. ' + root_cause_results[i][3] + '\n'
        msg = COMPREHEND_AGGREGATE_MESSAGE.replace(
                                '<desc>', exc_desc).replace('<rationale>', exc_rationale)
        while True:
            try:
                res = self.request(msg)
                aggregate_response = json.loads(res)
            except json.JSONDecodeError:
                self.logger.debug("[San2Patch] JSON decode error in aggregate comprehension response, retrying...")
                self.logger.debug("[San2Patch] response: " + res)
                continue
            break

        # save interaction
        self.save_with_json(msg, json.dumps(aggregate_response), 'comprehend_aggregate')
        
        self.root_cause_aggregate = aggregate_response
        self.root_causes_comprehend = root_cause_results

    ## 기존 san2patch에서는, trace 기반으로 어떤 target 수정할지 찾음.
    # -> Axolotl에서는 이미 target function 찾았다고 가정,
    # -> axolotl에서 target 은 함수내 어떤 line?

    # buggy function의 어떤 위치 수정할지 찾는 방식으로 수정
    # 현재 정보, comprehend_results, exception log, buggy function code, trace, 
    # -> 코드의 어떤부분을 수정하면 좋을지??
    # vuln_info_final 뭘까, aggregate_respons?
    def fault_localize(self):
        self.logger.info("Localizing fault locations...")

        # 필요한거: 
        # root_case description, root_cause rationale -> self.root_cause_aggregate
        # Exception Info -> self.exception_msg, self.exception_trace
        rc_desc = self.root_cause_aggregate.get('desc', '')
        rc_rationale = self.root_cause_aggregate.get('rationale', '')
        exc_msg = self.exception_msg
        exc_trace = self.exception_trace
        target_code = self.buggy_code
        msg = SELECT_LOCATIONS_MESSAGE.replace('<rc_desc>', rc_desc
                                               ).replace('<rc_rationale>', rc_rationale
                                                         ).replace('<exception_message>', exc_msg
                                                                   ).replace('<stack_trace>', exc_trace
                                                                             ).replace('<buggy_code>', target_code)
        fault_code_candidates = []
        self.logger.debug(f"[San2Patch] Sampling fix locations ({self.fl_branch_num} trials)...")
        for i in range(self.fl_branch_num):
            while True:
                try:
                    res = self.request(msg)
                    response = json.loads(res)
                except json.JSONDecodeError:
                    self.logger.debug("[San2Patch] JSON decode error in selected locations response, retrying...")
                    self.logger.debug("[San2Patch] response: " + res)
                    continue
                break
            # save_response
            self.save_with_json(msg, res, f'fault_localize_{i}')

            # single code snippet with rationale
            fault_code_candidates.append((response['code'], response['rationale']))

        # 3개(self.fl_branch_num) 후보군 -> 점수 부여 후, 1(self.fl_select_num)개 선택
        location_scores = dict()

        self.logger.debug("[San2Patch] Scoring and ranking candidate fix locations...")
        i = 0
        for loc in fault_code_candidates:
            msg = LOCATIONS_EVAL_MESSAGE
            msg = msg.replace('<rc_desc>', rc_desc
                                ).replace('<rc_rationale>', rc_rationale
                                    ).replace('<exception_message>', exc_msg
                                        ).replace('<stack_trace>', exc_trace
                                            ).replace('<buggy_code>', target_code)
            temp_msg = msg.replace('<candidate_code>', str(loc[0]))
            temp_msg = temp_msg.replace('<candidate_rationale>', str(loc[1]))
            while True:
                try:
                    res = self.request(temp_msg)
                    score_response = float(res)
                except ValueError:
                    self.logger.debug("[San2Patch] Value error in location score response, retrying...")
                    self.logger.debug("[San2Patch] response: " + res)
                    continue
                break
            # save interaction
            self.save_with_json(temp_msg, str(score_response), f'fault_localize_eval_loc{i}')
            i += 1

            location_scores[loc[0]] = (score_response, loc[1])
        self.logger.info(f'Number of candidate fix locations: {len(location_scores)}')
        
        self.logger.info(f'Sampling final fix location ...')
        # pruning(selecting) (greedy/sampling) -> 일단 greedy로 구현 / sampling 나중에 이곳에 구현
        final_locations = sorted(location_scores.items(), key=lambda x: x[1][0], reverse=True)[:self.fl_select_num]
        self.fault_localization = final_locations

    # fault_localization 결과 기반, fix strategy 생성
    def suggest_repair(self):
        self.logger.info("Suggesting repair strategies...")

        # 1. fix location 기반, fix strategy 생성
        self.logger.debug("[San2Patch] Generating candidate fix strategies...")

        msg = FIX_STRATEGY_MESSAGE.replace('<rc_desc>', self.root_cause_aggregate.get('desc'))
        msg = msg.replace('<rc_rationale>', self.root_cause_aggregate.get('rationale'))
        msg = msg.replace('<exception_message>', self.exception_msg
                    ).replace('<buggy_code>', self.buggy_code)
        
        strategy_candidates = []

        # fault_localization -> List[Tuple[str, Tuple[float, str]]]
        for loc in self.fault_localization:
            temp_msg = msg
            temp_msg = temp_msg.replace('<candidate_code>', str(loc[0]))
            temp_msg = temp_msg.replace('<candidate_rationale>', str(loc[1][1]))

            # Feedback from previous failed patches    
            if len(self.prev_failed_patches) > 0:
                self.feedback_trial += 1
                temp_msg += FIX_STRATEGY_FEEDBACK
                prev_patch_str = ''
                ## 이전 patch diff
                for i, patch in enumerate(self.prev_failed_patches):
                    prev_patch_str += f'{i}. ```\n{patch}\n```\n'
                temp_msg = temp_msg.replace('<prev_failed_patches>', prev_patch_str)

            # generate fix strategy for each location
            for i in range(self.sr_branch_num):
                while True:
                    try:
                        res = self.request(temp_msg)
                        strategy_response = json.loads(res)
                    except json.JSONDecodeError:
                        self.logger.debug("[San2Patch] JSON decode error in strategy response, retrying...")
                        self.logger.debug("[San2Patch] response: " + res)
                        continue
                    break

                # save interaction
                self.save_with_json(temp_msg, json.dumps(strategy_response), f'suggest_repair_trial{i}_fb{self.feedback_trial}')

                # strategy 수집 및 후보군에 넣기
                strategy = {
                    'location': loc[0],
                    'summary' : strategy_response['summary'],
                    'detailed_strategy': strategy_response['detailed_strategy'],
                    'rationale': strategy_response['rationale'],
                }
                strategy_candidates.append(strategy)

        ###########
        # 여기까지가 , 1 loc -> 3 strategy 생성 #
        # 이제 각 strategy 점수 부여 및, selecting #
        ##########

        strategies = []
        # scoring generted strategy
        self.logger.debug("[San2Patch] Evaluating and ranking candidate fix strategies...")
        # 지금 같은 loc마다 세개의 strategy 존재 -> strategy_candidates에
        i = 0
        for strategy in strategy_candidates:
            eval_msg = STRATEGY_EVAL_MESSAGE.replace('<rc_desc>', self.root_cause_aggregate.get('desc'))
            eval_msg = eval_msg.replace('<rc_rationale>', self.root_cause_aggregate.get('rationale'))
            eval_msg = eval_msg.replace('<exception_message>', self.exception_msg)
            eval_msg = eval_msg.replace('<target_code>', self.buggy_code)
            eval_msg = eval_msg.replace('<candidate_code>', str(strategy['location']))
            eval_msg = eval_msg.replace('<strat_summary>', str(strategy['summary']))
            eval_msg = eval_msg.replace('<strat_detail>', str(strategy['detailed_strategy']))
            eval_msg = eval_msg.replace('<strat_rationale>', str(strategy['rationale']))

            while True:
                try:
                    res = self.request(eval_msg)
                    score_response = float(res)
                except ValueError:
                    self.logger.debug("[San2Patch] Value error in strategy score response, retrying...")
                    self.logger.debug("[San2Patch] response: " + res)
                    continue
                break
            # save interaction
            self.save_with_json(eval_msg, str(score_response), f'suggest_repair_eval_strategy{i}_fb{self.feedback_trial}')
            i+=1

            strategy['eval_score'] = score_response
            strategies.append(strategy)

        # grouping -> 각 location마다 greedy/sampling -> loc별 final_strategies 선정
        # location 별로 strategy 묶어놓고
        grouped_strategies = dict()
        for strat in strategies:
            if strat['location'] not in grouped_strategies:
                grouped_strategies[strat['location']] = []
            grouped_strategies[strat['location']].append(strat)

        # location 마다 greedy/sampling -> final_strategies 선정

        self.logger.info(f'selecting final fix strategies ...')
        for _, strats in grouped_strategies.items():
            sorted_strats = sorted(strats, key=lambda s: s['eval_score'], reverse=True)
            select_size = min(self.sr_select_num, len(strats))
            self.final_strategies.extend(sorted_strats[:select_size])

            # sampling 방식 (나중에구현)
            # scores = [s['eval_score'] for s in strats]
            # select_size = min(1, len(strats))
            # ids = list(range(len(strats)))
            # ps = np.array(scores) / sum(scores)
            # select_ids = np.random.choice(
            #     ids,
            #     size=select_size,
            #     p=None,
            #     replace=False,
            # ).tolist()
            # final_strategies.extend([strats[i] for i in select_ids])




        # number -> fl_select_num * sr_select_num : 1 * 1 = 1개
        self.logger.debug(f"[San2Patch] Number of final fix strategies : {len(self.final_strategies)}")


    # 선정한 location별 strategy 기반 패치 생성
    def gen_patch(self):
        self.logger.info("[San2Patch] Generating patches...")

        # Generate patch
        self.logger.debug("[San2Patch] Generating candidate patches...")

        # 생성한 suggestion -> max_trial 만큼 패치 생성
        # 패치생성 필요한정보
        # <buggy_function_code>
        # <exception_message>
        # <rc_desc>
        # <rc_rationale>
        # <candidate_code>
        # <strat_summary>
        # <strat_detail>
        # <strat_rationale>
        
        # final_strategies 형식 / eval_score 높은순, loc 개, strategy 1개
        # [
        #   {
        #     'location': loc[0],
        #     'summary' : strategy_response['summary'],
        #     'detailed_strategy': strategy_response['detailed_strategy'],
        #     'desc': strategy_response['summary']
        #     'rationale': strategy_response['rationale']
        #     'eval_score' : ~ }
        # ]

        # 기존 san2patch -> 각 request에서 패치코드 몇개 만들지 모름
        # 여러개 만들도록하자
        i=0
        for strat in self.final_strategies:
            msg = GEN_PATCH_MESSAGE
            msg = msg.replace('<buggy_function_code>', self.buggy_code)
            msg = msg.replace('<exception_message>', self.exception_msg)
            msg = msg.replace('<rc_desc>', self.root_cause_aggregate.get('desc'))
            msg = msg.replace('<rc_rationale>', self.root_cause_aggregate.get('rationale'))
            msg = msg.replace('<candidate_code>', str(strat['location']))
            msg = msg.replace('<strat_summary>', str(strat['summary']))
            msg = msg.replace('<strat_detail>', str(strat['detailed_strategy']))
            msg = msg.replace('<strat_rationale>', str(strat['rationale']))

            if len(self.prev_failed_patches) > 0:
                # Feedback from previous failed patches
                msg += GEN_PATCH_FEEDBACK
                prev_patch_str = ''
                for j, patch in enumerate(self.prev_failed_patches):
                    prev_patch_str += f'{j}. ```\n{patch}\n```\n'
                msg = msg.replace('<prev_failed_patches>', prev_patch_str)
            
            while True:
                try:
                    res = self.request(msg)
                    response = json.loads(res)
                except json.JSONDecodeError as e:
                    self.logger.debug("[San2Patch] JSON decode error in patch generation response, retrying...")
                    self.logger.debug("[San2Patch] response: " + res)
                    err_msg = str(e)
                    success = False
                    for _ in range(10):
                        temp_msg = FIX_JSON_MESSAGE.replace('<original_answer>', res).replace(
                            '<error_msg>', err_msg)
                        res = self.request(temp_msg)
                        try:
                            response = json.loads(res)
                            for patch in response:
                                if 'patched_code' not in patch or 'rationale' not in patch:
                                    raise json.JSONDecodeError("Missing fields in patch", res, 0)
                        except json.JSONDecodeError as e:
                            err_msg = str(e)
                            continue
                        success = True
                        break
                    if not success:
                        continue
                break
            # save interaction
            self.save_with_json(msg, res, f'gen_patch_{i}_fb{self.feedback_trial}')
            i+=1

            for patch in response:
                patched_code = patch['patched_code'].replace('%%', '%') #? why replae?
                self.patches.append({
                    'location': strat['location'],
                    'patched_code': patched_code,
                    'rationale': patch['rationale'] if 'rationale' in patch else ''
                })

        self.logger.info(f'Number of generated patches: {len(self.patches)}')
        

    # Main patch generation workflow
    def run(self, output_dir:str):
        self.output_dir = output_dir
        # clean_up out_dir
        # if os.path.exists(self.output_dir):
        #     shutil.rmtree(self.output_dir)
        os.makedirs(self.output_dir, exist_ok=True)

        # initilaize/reset feedback info
        self.feedback_trial = 0
        self.prev_failed_patches = []

        ### 1. Exception understanding ###
        # : exception msg, trace, 등 의 정보로 root cause 분석
        # -> result in self.root_cause_aggregate, self.root_causes_comprehend
        # self.root_cause_aggregate : final root cause (모든 trial 결과 종합 버전)
        # self.root_causes_comprehend : trial 별 root cause (각 trial 결과 리스트 버전)
        self.comprehend()

        ### 2. Fault localization ###
        # : root cause 분석결과, buggy function code 기반, 함수 어떤 부분 수정할지?
        #  -> result in self.fault_localization = list[tuple[str, tuple[float, str]]]
        #  ex) [
            #     # 1등 후보 (점수 0.98)
            #     (
            #         "return a / b",              # Key: 코드 스니펫 (str)
            #         (0.98, "Divide by zero...")  # Value: (점수(float), 근거(str))
            #     ),

            #     # 2등 후보 (점수 0.85)
            #     (
            #         "if x is None:",             # Key: 코드 스니펫 (str)
            #         (0.85, "Null check...")      # Value: (점수(float), 근거(str))
            #     ),
            #     ...
            # ]
        self.fault_localize()
        
        ### 3. How to fix(repair suggestion) ###
        # : 선정된 location 기반, patch strategies 생성
        # -> result in self.final_strategies = list[dict[str, Any]]  fl_select_num * sr_select_num 개 만큼 있음
        #  axolotl에서는 1개 location, 1개 strategy니까, 1개   (3->1 loc , 3->1 strategy)
        self.suggest_repair()


        ### 4. generate patches ###
        # : patch strategies 기반, N개 패치 생성
        # -> result in self.patches = list[str]
        self.gen_patch()

        # return self.patches
    
    def feedback_patch_gen(self, prev_failed_patches: List[str]):
        self.prev_failed_patches.extend(prev_failed_patches)

        #initialize
        self.final_strategies = []
        self.patches = []

        # regenerate pathces with prev_failed_patches(start from suggest_repair)
        self.suggest_repair()
        self.gen_patch()

        # return self.patches
    
    def save_with_json(self, msg, response, filename):
        # request msg, model response -> json형식으로 filename 경로에 저장,  
        # result, request, response 등 json으로 경로에 저장
        # msg -> 프롬프트
        # response -> 모델응답 일단 str취급으로 다 저장?
        # filename -> 각 생성단계별 filename지정
        out_dir = os.path.join(self.output_dir,'model_interaction')
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f'{filename}.json')

        self.logger.debug(f'[San2Patch] Saving model_interaction to {out_path}')
        with open(out_path, 'w') as f:
            json.dump({
                'request': msg,
                'response': response
            }, f, indent=4)



    ### for ablation study ###
    # target buugy function 기반, potention excepion & root cause 분석하도록
    def comprehend_wo_dc(self) -> Tuple[dict, dict, list]:
        # axolotl-1 : exception log 기반 root cause 분석
        self.logger.debug("[San2Patch] Finding root cause ...")
        root_cause_results = []

        for i in range(self.max_trial):
            msg = COMPREHEND_MESSAGE_WO_DC.replace('<buggy_code>', self.buggy_code)
            
            while True:
                try:
                    res = self.request(msg)
                    comprehend_response = json.loads(res)
                except json.JSONDecodeError:
                    self.logger.debug("[San2Patch] JSON decode error in comprehend response, retrying...")
                    self.logger.debug("[San2Patch] response: " + res)
                    continue
                break
            # save interaction
            self.save_with_json(msg, json.dumps(comprehend_response), f'comprehend_{i}')
            
            # 여기서 max_trial만큼 description, rationale 모음
            exc_desc = comprehend_response['exception_description']
            exc_rationale = comprehend_response['rationale']
            root_cause_results.append((msg, comprehend_response, exc_desc, exc_rationale))

        # axolotl-2 : root cause aggregation
        # Aggregate results
        self.logger.debug("[San2Patch] Aggregating comprehension results and getting final results...")
        exc_desc = ''
        exc_rationale = ''
        for i in range(self.max_trial):
            exc_desc += f'{i}. ' + root_cause_results[i][2] + '\n'
            exc_rationale += f'{i}. ' + root_cause_results[i][3] + '\n'
        msg = COMPREHEND_AGGREGATE_MESSAGE.replace(
                                '<desc>', exc_desc).replace('<rationale>', exc_rationale)
        while True:
            try:
                res = self.request(msg)
                aggregate_response = json.loads(res)
            except json.JSONDecodeError:
                self.logger.debug("[San2Patch] JSON decode error in aggregate comprehension response, retrying...")
                self.logger.debug("[San2Patch] response: " + res)
                continue
            break

        # save interaction
        self.save_with_json(msg, json.dumps(aggregate_response), 'comprehend_aggregate')
        
        self.root_cause_aggregate = aggregate_response
        self.root_causes_comprehend = root_cause_results

    def fault_localize_wo_dc(self):
        self.logger.info("Localizing fault locations...")

        # 필요한거: 
        # root_case description, root_cause rationale -> self.root_cause_aggregate
        rc_desc = self.root_cause_aggregate.get('desc', '')
        rc_rationale = self.root_cause_aggregate.get('rationale', '')
        target_code = self.buggy_code
        msg = SELECT_LOCATIONS_MESSAGE_WO_DC.replace('<rc_desc>', rc_desc
                                               ).replace('<rc_rationale>', rc_rationale
                                                         ).replace('<buggy_code>', target_code)
        fault_code_candidates = []
        self.logger.debug(f"[San2Patch] Sampling fix locations ({self.fl_branch_num} trials)...")
        for i in range(self.fl_branch_num):
            while True:
                try:
                    res = self.request(msg)
                    response = json.loads(res)
                except json.JSONDecodeError:
                    self.logger.debug("[San2Patch] JSON decode error in selected locations response, retrying...")
                    self.logger.debug("[San2Patch] response: " + res)
                    continue
                break
            # save_response
            self.save_with_json(msg, res, f'fault_localize_{i}')

            # single code snippet with rationale
            fault_code_candidates.append((response['code'], response['rationale']))

        # 3개(self.fl_branch_num) 후보군 -> 점수 부여 후, 1(self.fl_select_num)개 선택
        location_scores = dict()

        self.logger.debug("[San2Patch] Scoring and ranking candidate fix locations...")
        i = 0
        for loc in fault_code_candidates:
            msg = LOCATIONS_EVAL_MESSAGE_WO_DC
            msg = msg.replace('<rc_desc>', rc_desc
                                ).replace('<rc_rationale>', rc_rationale
                                    ).replace('<buggy_code>', target_code)
            temp_msg = msg.replace('<candidate_code>', str(loc[0]))
            temp_msg = temp_msg.replace('<candidate_rationale>', str(loc[1]))
            while True:
                try:
                    res = self.request(temp_msg)
                    score_response = float(res)
                except ValueError:
                    self.logger.debug("[San2Patch] Value error in location score response, retrying...")
                    self.logger.debug("[San2Patch] response: " + res)
                    continue
                break
            # save interaction
            self.save_with_json(temp_msg, str(score_response), f'fault_localize_eval_loc{i}')
            i += 1

            location_scores[loc[0]] = (score_response, loc[1])
        self.logger.info(f'Number of candidate fix locations: {len(location_scores)}')
        
        self.logger.info(f'Sampling final fix location ...')
        # pruning(selecting) (greedy/sampling) -> 일단 greedy로 구현 / sampling 나중에 이곳에 구현
        final_locations = sorted(location_scores.items(), key=lambda x: x[1][0], reverse=True)[:self.fl_select_num]
        self.fault_localization = final_locations

    # fault_localization 결과 기반, fix strategy 생성
    def suggest_repair_wo_dc(self):
        self.logger.info("Suggesting repair strategies...")

        # 1. fix location 기반, fix strategy 생성
        self.logger.debug("[San2Patch] Generating candidate fix strategies...")

        msg = FIX_STRATEGY_MESSAGE_WO_DC.replace('<rc_desc>', self.root_cause_aggregate.get('desc'))
        msg = msg.replace('<rc_rationale>', self.root_cause_aggregate.get('rationale'))
        msg = msg.replace('<buggy_code>', self.buggy_code)
        
        strategy_candidates = []

        # fault_localization -> List[Tuple[str, Tuple[float, str]]]
        for loc in self.fault_localization:
            temp_msg = msg
            temp_msg = temp_msg.replace('<candidate_code>', str(loc[0]))
            temp_msg = temp_msg.replace('<candidate_rationale>', str(loc[1][1]))

            # Feedback from previous failed patches    
            if len(self.prev_failed_patches) > 0:
                self.feedback_trial += 1
                temp_msg += FIX_STRATEGY_FEEDBACK
                prev_patch_str = ''
                ## 이전 patch diff
                for i, patch in enumerate(self.prev_failed_patches):
                    prev_patch_str += f'{i}. ```\n{patch}\n```\n'
                temp_msg = temp_msg.replace('<prev_failed_patches>', prev_patch_str)

            # generate fix strategy for each location
            for i in range(self.sr_branch_num):
                while True:
                    try:
                        res = self.request(temp_msg)
                        strategy_response = json.loads(res)
                    except json.JSONDecodeError:
                        self.logger.debug("[San2Patch] JSON decode error in strategy response, retrying...")
                        self.logger.debug("[San2Patch] response: " + res)
                        continue
                    break

                # save interaction
                self.save_with_json(temp_msg, json.dumps(strategy_response), f'suggest_repair_trial{i}_fb{self.feedback_trial}')

                # strategy 수집 및 후보군에 넣기
                strategy = {
                    'location': loc[0],
                    'summary' : strategy_response['summary'],
                    'detailed_strategy': strategy_response['detailed_strategy'],
                    'rationale': strategy_response['rationale'],
                }
                strategy_candidates.append(strategy)
        strategies = []
        # scoring generted strategy
        self.logger.debug("[San2Patch] Evaluating and ranking candidate fix strategies...")
        # 지금 같은 loc마다 세개의 strategy 존재 -> strategy_candidates에
        i = 0
        for strategy in strategy_candidates:
            eval_msg = STRATEGY_EVAL_MESSAGE_WO_DC.replace('<rc_desc>', self.root_cause_aggregate.get('desc'))
            eval_msg = eval_msg.replace('<rc_rationale>', self.root_cause_aggregate.get('rationale'))
            eval_msg = eval_msg.replace('<target_code>', self.buggy_code)
            eval_msg = eval_msg.replace('<candidate_code>', str(strategy['location']))
            eval_msg = eval_msg.replace('<strat_summary>', str(strategy['summary']))
            eval_msg = eval_msg.replace('<strat_detail>', str(strategy['detailed_strategy']))
            eval_msg = eval_msg.replace('<strat_rationale>', str(strategy['rationale']))

            while True:
                try:
                    res = self.request(eval_msg)
                    score_response = float(res)
                except ValueError:
                    self.logger.debug("[San2Patch] Value error in strategy score response, retrying...")
                    self.logger.debug("[San2Patch] response: " + res)
                    continue
                break
            # save interaction
            self.save_with_json(eval_msg, str(score_response), f'suggest_repair_eval_strategy{i}_fb{self.feedback_trial}')
            i+=1

            strategy['eval_score'] = score_response
            strategies.append(strategy)

        # grouping -> 각 location마다 greedy/sampling -> loc별 final_strategies 선정
        # location 별로 strategy 묶어놓고
        grouped_strategies = dict()
        for strat in strategies:
            if strat['location'] not in grouped_strategies:
                grouped_strategies[strat['location']] = []
            grouped_strategies[strat['location']].append(strat)

        # location 마다 greedy/sampling -> final_strategies 선정

        self.logger.info(f'selecting final fix strategies ...')
        for _, strats in grouped_strategies.items():
            sorted_strats = sorted(strats, key=lambda s: s['eval_score'], reverse=True)
            select_size = min(self.sr_select_num, len(strats))
            self.final_strategies.extend(sorted_strats[:select_size])

            # sampling 방식 (나중에구현)
            # scores = [s['eval_score'] for s in strats]
            # select_size = min(1, len(strats))
            # ids = list(range(len(strats)))
            # ps = np.array(scores) / sum(scores)
            # select_ids = np.random.choice(
            #     ids,
            #     size=select_size,
            #     p=None,
            #     replace=False,
            # ).tolist()
            # final_strategies.extend([strats[i] for i in select_ids])


        # number -> fl_select_num * sr_select_num : 1 * 1 = 1개
        self.logger.debug(f"[San2Patch] Number of final fix strategies : {len(self.final_strategies)}")


    def gen_patch_wo_dc(self):
        self.logger.info("[San2Patch] Generating patches...")

        # Generate patch
        self.logger.debug("[San2Patch] Generating candidate patches...")

        i=0
        for strat in self.final_strategies:
            msg = GEN_PATCH_MESSAGE_WO_DC
            msg = msg.replace('<buggy_function_code>', self.buggy_code)
            msg = msg.replace('<rc_desc>', self.root_cause_aggregate.get('desc'))
            msg = msg.replace('<rc_rationale>', self.root_cause_aggregate.get('rationale'))
            msg = msg.replace('<candidate_code>', str(strat['location']))
            msg = msg.replace('<strat_summary>', str(strat['summary']))
            msg = msg.replace('<strat_detail>', str(strat['detailed_strategy']))
            msg = msg.replace('<strat_rationale>', str(strat['rationale']))

            if len(self.prev_failed_patches) > 0:
                # Feedback from previous failed patches
                msg += GEN_PATCH_FEEDBACK
                prev_patch_str = ''
                for j, patch in enumerate(self.prev_failed_patches):
                    prev_patch_str += f'{j}. ```\n{patch}\n```\n'
                msg = msg.replace('<prev_failed_patches>', prev_patch_str)
            
            while True:
                try:
                    res = self.request(msg)
                    response = json.loads(res)
                except json.JSONDecodeError as e:
                    self.logger.debug("[San2Patch] JSON decode error in patch generation response, retrying...")
                    self.logger.debug("[San2Patch] response: " + res)
                    err_msg = str(e)
                    success = False
                    for _ in range(10):
                        temp_msg = FIX_JSON_MESSAGE.replace('<original_answer>', res).replace(
                            '<error_msg>', err_msg)
                        res = self.request(temp_msg)
                        try:
                            response = json.loads(res)
                            for patch in response:
                                if 'patched_code' not in patch or 'rationale' not in patch:
                                    raise json.JSONDecodeError("Missing fields in patch", res, 0)
                        except json.JSONDecodeError as e:
                            err_msg = str(e)
                            continue
                        success = True
                        break
                    if not success:
                        continue
                break
            # save interaction
            self.save_with_json(msg, res, f'gen_patch_{i}_fb{self.feedback_trial}')
            i+=1

            for patch in response:
                patched_code = patch['patched_code'].replace('%%', '%') #? why replae?
                self.patches.append({
                    'location': strat['location'],
                    'patched_code': patched_code,
                    'rationale': patch['rationale'] if 'rationale' in patch else ''
                })

        self.logger.info(f'Number of generated patches: {len(self.patches)}')

    def run_wo_dc(self, output_dir:str):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.feedback_trial = 0
        self.prev_failed_patches = []
        self.comprehend_wo_dc()
        self.fault_localize_wo_dc()
        self.suggest_repair_wo_dc()
        self.gen_patch_wo_dc()

    # ablation 1 : without TOT(tree of thought)
    def singleton_patch_gen(self):
        self.logger.info("[San2Patch] Generating patches...")

        msg = SINGLETON_PATCH_GEN
        msg = msg.replace('<exception_message>', self.exception_msg)
        msg = msg.replace('<stack_trace>', self.exception_trace)
        msg = msg.replace('<buggy_code>', self.buggy_code)

        if len(self.prev_failed_patches) > 0:
            # Feedback from previous failed patches
            msg += GEN_PATCH_FEEDBACK
            prev_patch_str = ''
            for j, patch in enumerate(self.prev_failed_patches):
                prev_patch_str += f'{j}. ```\n{patch}\n```\n'
            msg = msg.replace('<prev_failed_patches>', prev_patch_str)

        while True:
            try:
                res = self.request(msg)
                response = json.loads(res)
            except json.JSONDecodeError as e:
                self.logger.debug("[San2Patch] JSON decode error in patch generation response, retrying...")
                self.logger.debug("[San2Patch] response: " + res)
                err_msg = str(e)
                success = False
                for _ in range(10):
                    temp_msg = FIX_JSON_MESSAGE.replace('<original_answer>', res).replace(
                        '<error_msg>', err_msg)
                    res = self.request(temp_msg)
                    try:
                        response = json.loads(res)
                        for patch in response:
                            if 'patched_code' not in patch:
                                raise json.JSONDecodeError("Missing fields in patch", res, 0)
                    except json.JSONDecodeError as e:
                        err_msg = str(e)
                        continue
                    success = True
                    break
                if not success:
                    continue
            break


        # save interaction
        self.save_with_json(msg, res, f'gen_patch_fb{self.feedback_trial}')
        patched_code = response['patched_code'].replace('%%', '%') #? why replae?
        self.patches.append({
            'patched_code': patched_code,
        })

        self.logger.info(f'Number of generated patches: {len(self.patches)}')
    # for ablation 1
    def run_singleton(self, output_dir:str):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

        # initilaize/reset feedback info
        self.feedback_trial = 0
        self.prev_failed_patches = []

        ### singleton patch generation ###
        self.singleton_patch_gen()

    def feedback_patch_gen_singleton(self, prev_failed_patches: List[str]):
        self.prev_failed_patches.extend(prev_failed_patches)

        #initialize
        self.final_strategies = []
        self.patches = []

        self.singleton_patch_gen() 