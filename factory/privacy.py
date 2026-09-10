"""Credential-safe diagnostics and native-format, metadata-only operation auditing.

Body redaction is not sufficient: invalid JSON, schema errors, SDK diagnostics and
traceback locals can also contain credentials. No workbench payload enters audit
storage, even on a failed request. The actual request delivered to the controller
is never modified. This module does not keep a global collection of user keys.
"""
from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable, Collection

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.background import BackgroundTasks

_SDK_LOGGERS = (
    "litellm", "openai", "anthropic", "httpx", "httpcore", "aiohttp",
    "e2b", "e2b_code_interpreter", "cubesandbox", "mcp",
)


def install_sdk_log_safety() -> None:
    """Protect even handlers installed later by an SDK or the upstream logger.

    A handler/root filter misses non-propagating SDK loggers. Sanitize records at
    creation, before any handler formats messages, arguments or exception locals.
    Keep only the logger, severity and callsite for transport diagnostics.
    """
    os.environ["LITELLM_LOG"] = "ERROR"
    os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
    previous = logging.getLogRecordFactory()
    if getattr(previous, "_rnd_credential_safe", False):
        return

    def safe_record(*args, **kwargs):
        record = previous(*args, **kwargs)
        name = record.name.lower()
        if any(name == prefix or (name.startswith(prefix + ".") or name.startswith(prefix + " ")) for prefix in _SDK_LOGGERS):
            record.msg = "SDK diagnostic omitted by credential policy; inspect the sanitized operation status"
            record.args = ()
            record.exc_info = None
            record.exc_text = None
            record.stack_info = None
        return record

    safe_record._rnd_credential_safe = True
    logging.setLogRecordFactory(safe_record)


def secure_host_logging() -> None:
    """Retain native log storage/rotation/correlation, never dump frame locals."""
    import sys
    from app.config.path_conf import LOG_DIR
    from app.config.setting import settings
    from app.core.logger import logger

    fmt = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}{extra[ctx]}"
    common = {"format": fmt, "level": settings.LOGGER_LEVEL, "backtrace": False, "diagnose": False}
    logger.configure(handlers=[
        {"sink": sys.stdout, **common},
        {"sink": str(LOG_DIR / "fastapiadmin.log"), "rotation": "00:00", "retention": 30,
         "compression": "gz", "encoding": "utf-8", **common},
    ])
    install_sdk_log_safety()


def metadata_only_route(
    upstream: type[APIRoute], writer: Callable, client_ip: Callable,
    methods: Collection[str],
    auth_exception: type[Exception] | None = None,
) -> type[APIRoute]:
    """Specialize OperationLogRoute using its record schema and database writer.

    Intentionally bypass the parent's body collector, NOT authentication,
    validation, dependency injection or existing response background tasks.
    """
    class CredentialSafeOperationLogRoute(upstream):
        def get_route_handler(self):
            original = APIRoute.get_route_handler(self)

            async def handle(request: Request):
                started = time.perf_counter()
                try:
                    response = await original(request)
                except RequestValidationError:
                    response = failure(request, 422, "请求参数无效，请检查字段类型、长度和格式")
                except HTTPException as exc:
                    # All domain HTTP exceptions use fixed, credential-free descriptions.
                    message = exc.detail if isinstance(exc.detail, str) else "请求未通过业务校验"
                    response = failure(request, exc.status_code, message, exc.headers)
                except Exception as exc:
                    # Preserve the host's authentication status without logging its payload.
                    # Missing-token CustomException defaults to 500 in the pinned host.
                    status = getattr(exc, "status_code", 500)
                    if auth_exception and isinstance(exc, auth_exception) and (
                        status in {401, 403} or not request.headers.get("authorization")
                    ):
                        status = 403 if status == 403 else 401
                        response = failure(request, status, "登录已失效，请重新登录" if status == 401 else "无权执行此操作")
                    else:
                        # No str(exc), logger.exception or chained traceback: SDK errors can carry secrets.
                        response = failure(request, 500, "操作未完成，请检查服务状态；敏感错误详情未写入日志")
                if request.method in methods:
                    ctx = getattr(request.state, "ctx", None)
                    record = {
                        "username": str(getattr(ctx, "user_username", None) or "unknown"),
                        "request_path": request.url.path,
                        "request_method": request.method,
                        "request_payload": '{"body":"[OMITTED_BY_CREDENTIAL_POLICY]"}',
                        "response_code": response.status_code,
                        "response_json": '{"body":"[OMITTED_BY_CREDENTIAL_POLICY]"}',
                        "process_time": f"{time.perf_counter() - started:.2f}s",
                        "description": self.summary or "AI研发平台操作",
                        "request_ip": client_ip(request),
                    }
                    tasks = BackgroundTasks()
                    if response.background is not None:
                        tasks.add_task(response.background)
                    tasks.add_task(writer, record)
                    response.background = tasks
                return response

            return handle

    return CredentialSafeOperationLogRoute


def failure(request: Request, status: int, message: str, headers=None) -> JSONResponse:
    legacy = bool(getattr(request.state, "factory_legacy", False))
    content = {"detail": message} if legacy else {"code": status, "msg": message, "data": None, "success": False}
    return JSONResponse(content, status_code=status, headers=headers)
