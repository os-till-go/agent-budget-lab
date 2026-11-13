"""Small real-model transports. Credentials stay in server environment only."""
import json
import copy
import os
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit


SCHEMA = {"type": "object", "properties": {"action": {"type": "string", "enum": ["answer", "read_log"]}, "choice": {"type": "string", "enum": ["A", "B", "C", "D", ""]}, "start": {"type": "integer"}, "count": {"type": "integer"}, "reason": {"type": "string"}}, "required": ["action", "choice", "start", "count", "reason"], "additionalProperties": False}


class ModelError(RuntimeError):
    pass


class ModelClient:
    def __init__(self):
        self.provider = os.getenv("ABL_PROVIDER", "ollama")
        if self.provider not in ("ollama", "compatible"):
            raise ValueError("ABL_PROVIDER 必须为 ollama 或 compatible")
        self.base = os.getenv("ABL_BASE_URL", "http://127.0.0.1:11434" if self.provider == "ollama" else "").rstrip("/")
        u = urlsplit(self.base)
        if u.username or u.password or u.query or u.fragment or not u.hostname:
            raise ValueError("模型地址不能包含凭据、查询或片段")
        if u.scheme != "https" and not (u.scheme == "http" and u.hostname in ("localhost", "127.0.0.1", "::1")):
            raise ValueError("远程模型必须使用 HTTPS；本地服务可使用 HTTP")
        self.model = os.getenv("ABL_MODEL", "llama3.2:1b" if self.provider == "ollama" else "")
        if not self.model:
            raise ValueError("请设置 ABL_MODEL")
        self.key = os.getenv("ABL_API_KEY", "")
        # Avoid sending credentials through ambient system proxies or redirects.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def metadata(self):
        return {"provider": self.provider, "model": self.model, "base_url": self.base, "temperature": 0, "max_output_tokens": 400, "context_tokens": 8192 if self.provider == "ollama" else None}

    def _request(self, path, payload=None, timeout=180):
        headers = {"Content-Type": "application/json"}
        if self.key:
            headers["Authorization"] = "Bearer " + self.key
        req = urllib.request.Request(self.base + path, data=json.dumps(payload).encode() if payload is not None else None, headers=headers)
        try:
            with self.opener.open(req, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            raise ModelError(f"模型服务 HTTP {exc.code}；未自动重试。请检查模型名、凭据和服务协议。") from None
        except (OSError, ValueError):
            raise ModelError("模型服务连接失败或返回非 JSON；未自动重试，已发生的服务端用量可能未知。") from None

    def status(self):
        data = self.metadata()
        data["api_key_configured"] = bool(self.key)
        data["available"] = None
        if self.provider == "ollama":
            try:
                tags = self._request("/api/tags", timeout=3).get("models", [])
                selected = next((m for m in tags if m["name"] == self.model), None)
                data.update(available=selected is not None, digest=selected.get("digest") if selected else None, installed_models=[m["name"] for m in tags])
            except ModelError as exc:
                data.update(available=False, error=str(exc))
        return data

    def chat(self, messages, seed=7, allow_query=False):
        started = time.perf_counter()
        if self.provider == "ollama":
            schema = copy.deepcopy(SCHEMA)
            if not allow_query:
                schema["properties"]["action"]["enum"] = ["answer"]
                schema["properties"]["choice"]["enum"] = ["A", "B", "C", "D"]
            raw = self._request("/api/chat", {"model": self.model, "messages": messages, "stream": False, "format": schema, "options": {"temperature": 0, "seed": seed, "num_predict": 400, "num_ctx": 8192}})
            content = raw.get("message", {}).get("content", "")
            usage = {"input_tokens": raw.get("prompt_eval_count"), "output_tokens": raw.get("eval_count"), "cached_input_tokens": None}
            model = raw.get("model", self.model)
            finish = raw.get("done_reason")
        else:
            raw = self._request("/chat/completions", {"model": self.model, "messages": messages, "temperature": 0, "max_tokens": 400, "response_format": {"type": "json_object"}})
            choices = raw.get("choices", [])
            if not choices:
                raise ModelError("兼容接口未返回 choices；不自动重试。")
            content = choices[0].get("message", {}).get("content", "")
            u = raw.get("usage", {})
            usage = {"input_tokens": u.get("prompt_tokens"), "output_tokens": u.get("completion_tokens"), "cached_input_tokens": u.get("prompt_tokens_details", {}).get("cached_tokens")}
            model, finish = raw.get("model", self.model), choices[0].get("finish_reason")
        return {"content": content, "usage": usage, "resolved_model": model, "finish_reason": finish, "elapsed_ms": round((time.perf_counter()-started)*1000, 2)}
