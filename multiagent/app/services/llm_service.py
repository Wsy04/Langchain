import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_project_env() -> None:
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    load_dotenv(PROJECT_ROOT / ".env.example", override=False)


load_project_env()


def mock_llm_json(prompt: str) -> dict[str, Any]:
    return {
        "summary": "Mock 生成结果",
        "items": [],
        "prompt_preview": prompt[:200],
    }


class LLMService:
    def __init__(self) -> None:
        self.mode = os.getenv("LLM_MODE", "mock").lower()
        self.model_name = os.getenv("MODEL_NAME", "deepseek-v4-flash")
        self.base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("DEEPSEEK_API_BASE_URL") or None
        self.api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY") or None

    def invoke_json(self, prompt: str) -> dict[str, Any]:
        if self.mode == "mock":
            return mock_llm_json(prompt)

        try:
            content = self._invoke_real_llm(prompt)
            return self._parse_json(content)
        except Exception as exc:
            return {
                "error": str(exc),
                "mode": self.mode,
                "model": self.model_name,
            }

    def _invoke_real_llm(self, prompt: str) -> str:
        from langchain_openai import ChatOpenAI

        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY or OPENAI_API_KEY is required when LLM_MODE is not mock")

        llm = ChatOpenAI(
            model=self.model_name,
            api_key=self.api_key,
            base_url=self.base_url,
        )
        response = llm.invoke(prompt)
        return str(response.content)

    @staticmethod
    def _parse_json(content: str) -> dict[str, Any]:
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return {
                "content": content,
                "warning": "LLM response is not valid JSON",
            }

        if isinstance(parsed, dict):
            return parsed

        return {"items": parsed}


llm_service = LLMService()


def invoke_llm_json(prompt: str) -> dict[str, Any]:
    return llm_service.invoke_json(prompt)
