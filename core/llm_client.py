import os
import json
from typing import Optional
from openai import OpenAI

DEFAULT_MODEL = "deepseek-v4-flash"

QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


class LLMClient:
    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.model = model
        resolved_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not resolved_key:
            raise ValueError(
                "API key 未设置。请通过参数传入 api_key 或设置环境变量 OPENAI_API_KEY"
            )
        env_url = os.environ.get("BASE_URL")
        if base_url:
            resolved_url = base_url
        elif env_url:
            resolved_url = env_url
        else:
            resolved_url = QWEN_BASE_URL
        self.client = OpenAI(api_key=resolved_key, base_url=resolved_url)

    def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.7) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
        )
        return response.choices[0].message.content or ""

    def generate_json(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> dict:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        return json.loads(content) if content else {}