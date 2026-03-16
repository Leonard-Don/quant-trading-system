"""
请求ID中间件
为每个请求生成唯一ID，便于日志追踪
"""

import uuid
import logging
from contextvars import ContextVar
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from typing import Optional

logger = logging.getLogger(__name__)

# 上下文变量，用于在请求处理期间存储request_id
_request_id_ctx_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def get_request_id() -> Optional[str]:
    """
    获取当前请求的ID

    Returns:
        当前请求的ID，如果不存在则返回None
    """
    return _request_id_ctx_var.get()


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    请求ID中间件
    为每个请求生成或使用现有的唯一ID
    """

    def __init__(self, app, header_name: str = "X-Request-ID"):
        """
        Args:
            app: FastAPI应用实例
            header_name: 请求ID的HTTP头名称
        """
        super().__init__(app)
        self.header_name = header_name
        logger.info(f"请求ID中间件初始化: 头名称={header_name}")

    async def dispatch(self, request: Request, call_next):
        """
        处理请求

        Args:
            request: HTTP请求
            call_next: 下一个中间件或路由处理器

        Returns:
            HTTP响应
        """
        # 尝试从请求头中获取request_id，如果不存在则生成新的
        request_id = request.headers.get(self.header_name)
        if not request_id:
            request_id = str(uuid.uuid4())

        # 将request_id存储在上下文变量中
        _request_id_ctx_var.set(request_id)

        # 记录请求开始
        logger.info(
            f"请求开始: {request.method} {request.url.path}",
            extra={"request_id": request_id},
        )

        try:
            # 调用下一个处理器
            response = await call_next(request)

            # 将request_id添加到响应头中
            response.headers[self.header_name] = request_id

            # 记录请求完成
            logger.info(
                f"请求完成: {request.method} {request.url.path} "
                f"状态码={response.status_code}",
                extra={"request_id": request_id},
            )

            return response

        except Exception as e:
            # 记录请求错误
            logger.error(
                f"请求错误: {request.method} {request.url.path} " f"错误={str(e)}",
                extra={"request_id": request_id},
                exc_info=True,
            )
            raise

        finally:
            # 清理上下文变量
            _request_id_ctx_var.set(None)


class RequestIDFilter(logging.Filter):
    """
    日志过滤器，将request_id添加到日志记录中
    """

    def filter(self, record):
        """
        为日志记录添加request_id字段

        Args:
            record: 日志记录

        Returns:
            True（总是返回True以不过滤任何日志）
        """
        record.request_id = get_request_id() or "N/A"
        return True
