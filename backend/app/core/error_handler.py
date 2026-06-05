"""
统一错误处理中间件和异常类
"""
import logging
import traceback
from datetime import datetime
from typing import Any, Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


# ==================== 自定义异常类 ====================

class AppException(Exception):
    """应用基础异常类"""
    def __init__(
        self,
        message: str,
        error_code: str = "INTERNAL_ERROR",
        status_code: int = 500,
        details: Optional[Any] = None
    ):
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details
        super().__init__(self.message)


class ValidationError(AppException):
    """数据验证错误"""
    def __init__(self, message: str, details: Optional[Any] = None):
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            status_code=400,
            details=details
        )


# ==================== 错误响应格式化 ====================

def create_error_response(
    error_code: str,
    message: str,
    status_code: int,
    details: Optional[Any] = None,
    request_id: Optional[str] = None
) -> dict:
    """创建统一的错误响应格式"""
    response = {
        "success": False,
        "error": {
            "code": error_code,
            "message": message,
            "timestamp": datetime.now().isoformat()
        }
    }

    if details:
        response["error"]["details"] = details

    if request_id:
        response["error"]["request_id"] = request_id

    return response


# ==================== 异常处理器注册 ====================

def register_exception_handlers(app):
    """注册 FastAPI 异常处理器"""

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        return JSONResponse(
            status_code=exc.status_code,
            content=create_error_response(
                error_code=exc.error_code,
                message=exc.message,
                status_code=exc.status_code,
                details=exc.details
            )
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=create_error_response(
                error_code="HTTP_ERROR",
                message=str(exc.detail),
                status_code=exc.status_code
            )
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled exception: {exc!s}\n{traceback.format_exc()}")
        return JSONResponse(
            status_code=500,
            content=create_error_response(
                error_code="INTERNAL_ERROR",
                message="服务器内部错误",
                status_code=500
            )
        )
