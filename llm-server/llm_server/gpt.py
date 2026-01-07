from openai import OpenAI
import os
from .model import *


class GPT5Model(BaseModel):
    def __init__(self):
        super().__init__()
        self.logger.info('Initializing GPT-5 model client...')
        self.api_key = os.environ['OPENAI_API_KEY']
        self.client = OpenAI(api_key=self.api_key)

    def request(self, system_msg: str, prompt: str) -> str:
        response = self.client.chat.completions.create(
            messages=[
                {'role': 'developer', 'content': system_msg},
                {'role': 'user', 'content': prompt},
            ],
            model='gpt-5.2',
            max_completion_tokens=10240,
        )
        self.logger.debug(f'Generation outputs: {response}')

        return response.choices[0].message.content
    
class GPT4NanoModel(BaseModel):
    def __init__(self):
        super().__init__()
        self.logger.info('Initializing GPT-4 nano model client...')
        self.api_key = os.environ['OPENAI_API_KEY']
        self.client = OpenAI(api_key=self.api_key)

    def request(self, system_msg: str, prompt: str) -> str:
        response = self.client.chat.completions.create(
            messages=[
                {'role': 'system', 'content': system_msg},
                {'role': 'user', 'content': prompt},
            ],
            model='gpt-4.1-nano',
            max_completion_tokens=4096,
        )
        self.logger.debug(f'Generation outputs: {response}')

        return response.choices[0].message.content