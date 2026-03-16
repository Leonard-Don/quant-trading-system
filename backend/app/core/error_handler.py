"""
统一错误处理中间件和异常类
"""
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import traceback
import logging
from typing import Optional, Any
from datetime import datetime

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


class NotFoundError(AppException):
    """资源未找到错误"""
    def __init__(self, resource: str, identifier: str = None):
        message = f"{resource} 未找到"
        if identifier:
            message = f"{resource} '{identifier}' 未找到"
        super().__init__(
            message=message,
            error_code="NOT_FOUND",
            status_code=404
        )


class ExternalServiceError(AppException):
    """外部服务调用错误"""
    def __init__(self, service: str, message: str = None):
        super().__init__(
            message=message or f"外部服务 {service} 调用失败",
            error_code="EXTERNAL_SERVICE_ERROR",
            status_code=503
        )


class DataFetchError(AppException):
    """数据获取错误"""
    def __init__(self, symbol: str = None, message: str = None):
        error_message = message or "数据获取失败"
        if symbol:
            error_message = f"获取 {symbol} 数据失败"
        super().__init__(
            message=error_message,
            error_code="DATA_FETCH_ERROR",
            status_code=502,
            details={"symbol": symbol} if symbol else None
        )


class RateLimitError(AppException):
    """请求频率限制错误"""
    def __init__(self, retry_after: int = 60):
        super().__init__(
            message=f"请求过于频繁，请 {retry_after} 秒后重试",
            error_code="RATE_LIMIT_EXCEEDED",
            status_code=429,
            details={"retry_after": retry_after}
        )


class AuthenticationError(AppException):
    """认证错误"""
    def __init__(self, message: str = "认证失败"):
        super().__init__(
            message=message,
            error_code="AUTHENTICATION_ERROR",
            status_code=401
        )


# ==================== 错误响应格式化 ====================

def create_error_response(
    error_code: str,
    message: str,
    status_code: int,
    details: Optional[Any] = None,
    request_id: str = None
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


# ==================== 错误处理中间件 ====================

class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """全局错误处理中间件"""
    
    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response
            
        except AppException as e:
            # 处理自定义应用异常
            logger.warning(f"Application error: {e.error_code} - {e.message}")
            return JSONResponse(
                status_code=e.status_code,
                content=create_error_response(
                    error_code=e.error_code,
                    message=e.message,
                    status_code=e.status_code,
                    details=e.details
                )
            )
            
        except HTTPException as e:
            # 处理 FastAPI HTTP 异常
            logger.warning(f"HTTP error: {e.status_code} - {e.detail}")
            return JSONResponse(
                status_code=e.status_code,
                content=create_error_response(
                    error_code="HTTP_ERROR",
                    message=str(e.detail),
                    status_code=e.status_code
                )
            )
            
        except Exception as e:
            # 处理未预期的异常
            logger.error(f"Unexpected error: {str(e)}\n{traceback.format_exc()}")
            return JSONResponse(
                status_code=500,
                content=create_error_response(
                    error_code="INTERNAL_ERROR",
                    message="服务器内部错误，请稍后重试",
                    status_code=500,
                    details={"error_type": type(e).__name__} if __debug__ else None
                )
            )


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
        logger.error(f"Unhandled exception: {str(exc)}\n{traceback.format_exc()}")
        return JSONResponse(
            status_code=500,
            content=create_error_response(
                error_code="INTERNAL_ERROR",
                message="服务器内部错误",
                status_code=500
            )
        )
