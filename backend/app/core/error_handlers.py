from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "") or request.headers.get("x-request-id", ""))


def _error_payload(
    *,
    message: str,
    code: str,
    request: Request,
    status_code: int,
    details=None,
) -> dict:
    return {
        "error": {
            "message": message,
            "code": code,
            "status": status_code,
            "request_id": _request_id(request),
            "details": details,
        }
    }


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        message = exc.detail if isinstance(exc.detail, str) else "请求失败"
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(
                message=message,
                code="http_error",
                request=request,
                status_code=exc.status_code,
                details=exc.detail,
            ),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content=_error_payload(
                message="请求参数无效",
                code="validation_error",
                request=request,
                status_code=422,
                details=exc.errors(),
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("unhandled request error rid=%s", _request_id(request))
        return JSONResponse(
            status_code=500,
            content=_error_payload(
                message="服务器内部错误，请查看日志",
                code="internal_error",
                request=request,
                status_code=500,
            ),
        )
