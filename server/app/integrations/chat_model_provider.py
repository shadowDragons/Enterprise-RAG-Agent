"""封装回答生成用的聊天模型调用。

这个模块负责：
- 使用 LangChain message 结构组织输入消息
- 通过 OpenAI 兼容 `/chat/completions` 协议调用真实模型
- 在需要时把上游 SSE chunk 解析成稳定的 delta 事件
- 把第三方异常收口成稳定错误，交给上层统一处理
"""

import json
import ssl
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from urllib import error, request

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.core.config import get_settings


class ChatModelUnavailableError(RuntimeError):
    """当前环境没有可用聊天模型时抛出。"""


class ChatModelInvocationError(RuntimeError):
    """聊天模型调用失败时抛出。"""


@dataclass
class ChatModelResponse:
    content: str
    model_name: str
    backend_name: str


@dataclass
class ChatModelChunk:
    delta: str
    model_name: str
    backend_name: str
    finish_reason: str | None = None


class ChatBackend(ABC):
    """聊天模型后端的统一抽象。"""

    name: str

    @abstractmethod
    def invoke(
        self,
        *,
        messages: list[BaseMessage],
        model: str,
        temperature: float,
    ) -> ChatModelResponse:
        raise NotImplementedError

    @abstractmethod
    def stream(
        self,
        *,
        messages: list[BaseMessage],
        model: str,
        temperature: float,
    ) -> Iterator[ChatModelChunk]:
        raise NotImplementedError


class OpenAICompatibleChatBackend(ChatBackend):
    """调用遵循 OpenAI Chat Completions 协议的远程接口。"""

    name = "openai_compatible"

    def __init__(self) -> None:
        self.settings = get_settings()

    def invoke(
        self,
        *,
        messages: list[BaseMessage],
        model: str,
        temperature: float,
    ) -> ChatModelResponse:
        try:
            with self._open_response(
                messages=messages,
                model=model,
                temperature=temperature,
                stream=False,
            ) as response:
                body = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise ChatModelInvocationError(
                f"聊天模型请求失败，HTTP {exc.code}: {detail[:300]}"
            ) from exc
        except error.URLError as exc:
            raise ChatModelInvocationError(f"聊天模型请求失败：{exc.reason}") from exc

        choices = body.get("choices", [])
        if not choices:
            raise ChatModelInvocationError("聊天模型返回为空，未包含 choices。")

        message = choices[0].get("message", {})
        content = self._extract_text_content(message.get("content", ""))
        if not content:
            raise ChatModelInvocationError("聊天模型返回了空内容。")

        resolved_model_name = str(body.get("model") or model)
        return ChatModelResponse(
            content=content.strip(),
            model_name=resolved_model_name,
            backend_name=self.name,
        )

    def stream(
        self,
        *,
        messages: list[BaseMessage],
        model: str,
        temperature: float,
    ) -> Iterator[ChatModelChunk]:
        resolved_model_name = model
        emitted_any_chunk = False
        try:
            with self._open_response(
                messages=messages,
                model=model,
                temperature=temperature,
                stream=True,
            ) as response:
                # OpenAI 兼容流式接口本质是 SSE；这里把 data: JSON 逐行解析成
                # 稳定的 delta 事件，避免上层直接感知第三方协议细节。
                for raw_line in response:
                    line = raw_line.decode("utf-8", errors="ignore").strip()
                    if not line or not line.startswith("data:"):
                        continue

                    payload = line.removeprefix("data:").strip()
                    if payload == "[DONE]":
                        break

                    try:
                        body = json.loads(payload)
                    except json.JSONDecodeError as exc:
                        raise ChatModelInvocationError(
                            f"聊天模型流式返回无法解析：{payload[:200]}"
                        ) from exc

                    if "error" in body:
                        raise ChatModelInvocationError(
                            f"聊天模型流式返回错误：{body['error']}"
                        )

                    choices = body.get("choices", [])
                    if not choices:
                        continue

                    resolved_model_name = str(body.get("model") or resolved_model_name)
                    choice = choices[0]
                    delta = self._extract_text_content(
                        (choice.get("delta") or {}).get("content", "")
                    )
                    if not delta:
                        continue

                    emitted_any_chunk = True
                    yield ChatModelChunk(
                        delta=delta,
                        model_name=resolved_model_name,
                        backend_name=self.name,
                        finish_reason=choice.get("finish_reason"),
                    )
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise ChatModelInvocationError(
                f"聊天模型流式请求失败，HTTP {exc.code}: {detail[:300]}"
            ) from exc
        except error.URLError as exc:
            raise ChatModelInvocationError(
                f"聊天模型流式请求失败：{exc.reason}"
            ) from exc

        if not emitted_any_chunk:
            raise ChatModelInvocationError("聊天模型流式返回为空。")

    def _message_to_payload(self, message: BaseMessage) -> dict[str, str]:
        if isinstance(message, SystemMessage):
            role = "system"
        elif isinstance(message, AIMessage):
            role = "assistant"
        elif isinstance(message, HumanMessage):
            role = "user"
        else:
            role = str(getattr(message, "type", "user"))

        return {
            "role": role,
            "content": self._extract_text_content(message.content),
        }

    def _extract_text_content(self, content) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        parts.append(str(item.get("text", "")))
                    elif "content" in item:
                        parts.append(str(item.get("content", "")))
            return "\n".join(part for part in parts if part).strip()
        return str(content or "")

    def _open_response(
        self,
        *,
        messages: list[BaseMessage],
        model: str,
        temperature: float,
        stream: bool,
    ):
        endpoint = self.settings.resolved_llm_api_base.rstrip("/") + "/chat/completions"
        payload = {
            "model": model,
            "messages": [self._message_to_payload(item) for item in messages],
            "temperature": temperature,
            "stream": stream,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.settings.resolved_llm_api_key}",
        }
        http_request = request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        ssl_context = None
        if not self.settings.llm_ssl_verify:
            ssl_context = ssl._create_unverified_context()
        return request.urlopen(
            http_request,
            timeout=self.settings.llm_timeout_seconds,
            context=ssl_context,
        )


class ChatModelService:
    """解析当前可用后端，并为上层提供统一的 invoke 接口。"""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.backend, self.unavailability_reason = self._resolve_backend()
        self.active_backend_name = self.backend.name if self.backend else "unavailable"

    def _resolve_backend(self) -> tuple[ChatBackend | None, str | None]:
        provider = self.settings.llm_provider.lower().strip()
        if provider == "local":
            return None, "llm_provider=local，当前未启用真实聊天模型。"

        if provider in {"auto", "openai"}:
            if not self.settings.resolved_llm_api_base:
                return None, "未配置可用的聊天模型 base URL。"
            if not self.settings.resolved_llm_api_key:
                return None, "未配置可用的聊天模型 API key。"
            return OpenAICompatibleChatBackend(), None

        return None, f"不支持的 llm_provider：{self.settings.llm_provider}"

    def is_available(self) -> bool:
        return self.backend is not None

    def describe_backend(self) -> str:
        if self.backend:
            return self.backend.name
        return self.unavailability_reason or "unavailable"

    def invoke(
        self,
        *,
        messages: list[BaseMessage],
        model: str,
        temperature: float | None = None,
    ) -> ChatModelResponse:
        if not self.backend:
            raise ChatModelUnavailableError(
                self.unavailability_reason or "当前环境没有可用的聊天模型后端。"
            )

        resolved_model = model.strip()
        if not resolved_model:
            raise ChatModelUnavailableError("当前未配置可用的聊天模型名称。")

        resolved_temperature = (
            self.settings.llm_temperature if temperature is None else temperature
        )
        response = self.backend.invoke(
            messages=messages,
            model=resolved_model,
            temperature=resolved_temperature,
        )
        self.active_backend_name = response.backend_name
        return response

    def stream(
        self,
        *,
        messages: list[BaseMessage],
        model: str,
        temperature: float | None = None,
    ) -> Iterator[ChatModelChunk]:
        if not self.backend:
            raise ChatModelUnavailableError(
                self.unavailability_reason or "当前环境没有可用的聊天模型后端。"
            )

        resolved_model = model.strip()
        if not resolved_model:
            raise ChatModelUnavailableError("当前未配置可用的聊天模型名称。")

        resolved_temperature = (
            self.settings.llm_temperature if temperature is None else temperature
        )
        return self.backend.stream(
            messages=messages,
            model=resolved_model,
            temperature=resolved_temperature,
        )
