from vllm import LLM, SamplingParams
import torch
from .model import *


class Llama4ScoutModel(BaseModel):
    MODEL_NAME = 'meta-llama/Llama-4-Scout-17B-16E-Instruct'

    def __init__(self, tensor_parallel_size: int = 1, max_model_len: int = 8192):
        super().__init__()
        self.logger.info('Initializing Llama-4 Scout model client...')
        self.model = LLM(model=self.MODEL_NAME,
                         dtype='bfloat16',
                         tensor_parallel_size=tensor_parallel_size,
                         max_model_len=max_model_len,
                         gpu_memory_utilization=0.85)

    def request(self, system_msg: str, prompt: str):
        message = [
            {
                "role": "system",
                "content": system_msg
            },
            {
                "role": "user",
                "content": prompt
            }
        ]

        inputs = self.model.get_tokenizer().apply_chat_template(
            message,
            add_generation_prompt=True,
            tokenize=False
        )
        sampling_params = SamplingParams(max_tokens=2048, temperature=0.1)

        outputs = self.model.generate(
            [inputs],
            sampling_params=sampling_params
        )
        self.logger.debug(f'Generation outputs: {outputs[0].outputs[0]}')

        return outputs[0].outputs[0].text
