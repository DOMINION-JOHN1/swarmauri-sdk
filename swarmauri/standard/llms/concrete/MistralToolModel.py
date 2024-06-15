import json
from typing import List
from mistralai.client import MistralClient
from swarmauri.standard.models.base.LLMBase import LLMBase

class MistralModel(LLMBase):
    api_key: str
    allowed_models: List[str] = ['open-mixtral-8x22b', 
    'mistral-small-latest',
    'mistral-large-latest',
    ]
    name: str = "open-mixtral-8x22b"

    def predict(self, 
        messages, 
        tools=None, 
        tool_choice=None, 
        temperature=0.7, 
        max_tokens=1024, 
        safe_prompt: bool = False):

        client =  MistralClient(api_key=self.api_key)

        if tools and not tool_choice:
            tool_choice = "auto"
            
        response = client.chat.completions.create(
            model=self.name,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=tool_choice,
            safe_prompt=safe_prompt
        )
        return response