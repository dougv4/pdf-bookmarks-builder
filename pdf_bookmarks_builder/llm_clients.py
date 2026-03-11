from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any
from urllib import error, request


class ProviderClient(ABC):
    def __init__(self, api_key: str, model: str, timeout_seconds: int = 90) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    @abstractmethod
    def generate(self, prompt: str) -> str:
        raise NotImplementedError

    def _post_json(self, url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        for key, value in headers.items():
            req.add_header(key, value)
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code}: {raw}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Falha de rede: {exc.reason}") from exc


class OpenAIClient(ProviderClient):
    def generate(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "temperature": 0.1,
            "messages": [
                {
                    "role": "system",
                    "content": "Voce organiza sumarios de livros em marcadores de PDF. Responda apenas no formato pedido.",
                },
                {"role": "user", "content": prompt},
            ],
        }
        data = self._post_json(
            "https://api.openai.com/v1/chat/completions",
            payload,
            {"Authorization": f"Bearer {self.api_key}"},
        )
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("Resposta invalida da API da OpenAI.") from exc
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Resposta vazia da API da OpenAI.")
        return content.strip()


class GeminiClient(ProviderClient):
    def generate(self, prompt: str) -> str:
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1},
        }
        data = self._post_json(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}",
            payload,
            {},
        )
        try:
            parts = data["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("Resposta invalida da API do Gemini.") from exc
        text_parts = [part.get("text", "") for part in parts if isinstance(part, dict)]
        output = "\n".join(part for part in text_parts if part).strip()
        if not output:
            raise RuntimeError("Resposta vazia da API do Gemini.")
        return output
