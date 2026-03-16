"""
增强的错误处理模块
"""

import traceback
import sys
from typing import Any, Dict, Optional, Type, Union, Callable
from datetime import datetime
import logging
from functools import wraps

# 模块级别的logger
logger = logging.getLogger(__name__)


def _sanitize_value(value, max_length=200):
    """清理敏感信息并限制长度"""
    # 敏感字段列表
    sensitive_keys = {
        "password",
        "passwd",
        "pwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "private_key",
        "credential",
        "auth",
        "authorization",
    }

    if isinstance(value, dict):
        sanitized = {}
        for k, v in value.items():
            key_lower = str(k).lower()
            if any(sensitive in key_lower for sensitive in sensitive_keys):
                sanitized[k] = "***REDACTED***"
            else:
                sanitized[k] = _sanitize_value(v, max_length)
        return sanitized
    elif isinstance(value, (list, tuple)):
        return type(value)(_sanitize_value(item, max_length) for item in value)
    else:
        str_value = str(value)
        if len(str_value) > max_length:
            return str_value[:max_length] + "..."
        return str_value


class ErrorContext:
    """错误上下文信息"""

    def __init__(self):
        self.context_data = {}
        self.error_history = []

    def add_context(self, key: str, value: Any) -> None:
        """添加上下文信息"""
        self.context_data[key] = value

    def get_context(self) -> Dict[str, Any]:
        """获取所有上下文信息"""
        return self.context_data.copy()

    def record_error(self, error: Exception, context: Optional[Dict] = None) -> None:
        """记录错误"""
        error_info = {
            "timestamp": datetime.now().isoformat(),
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": traceback.format_exc(),
            "context": context or {},
        }
        self.error_history.append(error_info)

    def get_error_history(self) -> list:
        """获取错误历史"""
        return self.error_history.copy()


class ErrorHandler:
    """错误处理器"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.error_callbacks = {}
        self.global_context = ErrorContext()

    def register_callback(
        self, error_type: Type[Exception], callback: Callable
    ) -> None:
        """注册错误回调函数"""
        self.error_callbacks[error_type] = callback

    def handle_error(
        self, error: Exception, context: Optional[Dict] = None, reraise: bool = True
    ) -> Optional[Any]:
        """处理错误"""
        # 记录错误到全局上下文
        self.global_context.record_error(error, context)

        # 构建错误信息
        error_info = {
            "error_type": type(error).__name__,
            "error_message": str(error),
            "timestamp": datetime.now().isoformat(),
            "context": context or {},
            "traceback": traceback.format_exc(),
        }

        # 记录日志
        error_msg = (
            f"Error occurred: {error_info['error_type']}: "
            f"{error_info['error_message']}"
        )
        self.logger.error(error_msg, extra={"error_info": error_info})

        # 调用特定错误类型的回调
        error_type = type(error)
        if error_type in self.error_callbacks:
            try:
                result = self.error_callbacks[error_type](error, context)
                if result is not None:
                    return result
            except Exception as callback_error:
                self.logger.error(f"Error callback failed: {callback_error}")

        # 重新抛出异常
        if reraise:
            raise error

        return None

    def create_error_report(self) -> Dict[str, Any]:
        """创建错误报告"""
        return {
            "timestamp": datetime.now().isoformat(),
            "error_history": self.global_context.get_error_history(),
            "global_context": self.global_context.get_context(),
            "system_info": {"python_version": sys.version, "platform": sys.platform},
        }

    def clear_history(self) -> None:
        """清空错误历史"""
        self.global_context.error_history.clear()


# 全局错误处理器
error_handler = ErrorHandler()


def handle_errors(
    error_types: Union[Type[Exception], tuple] = Exception,
    context_func: Optional[Callable] = None,
    reraise: bool = True,
    default_return: Any = None,
):
    """错误处理装饰器"""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except error_types as e:
                # 构建上下文信息并清理敏感数据
                context = {
                    "function": func.__name__,
                    "args": _sanitize_value(args),
                    "kwargs": _sanitize_value(kwargs),
                }

                if context_func:
                    try:
                        additional_context = context_func(*args, **kwargs)
                        context.update(_sanitize_value(additional_context))
                    except Exception as e:
                        # 记录上下文函数错误但不中断主流程
                        logger.debug(f"Failed to add additional context: {e}")

                # 处理错误
                result = error_handler.handle_error(e, context, reraise=False)

                if reraise:
                    raise e
                else:
                    return result if result is not None else default_return

        return wrapper

    return decorator


def safe_execute(func: Callable, *args, default: Any = None, **kwargs) -> Any:
    """安全执行函数，捕获所有异常"""
    try:
        return func(*args, **kwargs)
    except Exception as e:
        # 清理敏感信息后再记录
        sanitized_context = {
            "function": func.__name__,
            "args": _sanitize_value(args),
            "kwargs": _sanitize_value(kwargs),
        }
        error_handler.handle_error(e, sanitized_context, reraise=False)
        return default


class CircuitBreaker:
    """熔断器模式实现"""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: Type[Exception] = Exception,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception

        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN

        self.logger = logging.getLogger(f"{__name__}.CircuitBreaker")

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """通过熔断器调用函数"""
        if self.state == "OPEN":
            if self._should_attempt_reset():
                self.state = "HALF_OPEN"
                self.logger.info("Circuit breaker state: HALF_OPEN")
            else:
                raise Exception("Circuit breaker is OPEN")

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise e

    def _should_attempt_reset(self) -> bool:
        """检查是否应该尝试重置熔断器"""
        if self.last_failure_time is None:
            return False

        return (
            datetime.now() - self.last_failure_time
        ).seconds >= self.recovery_timeout

    def _on_success(self) -> None:
        """成功时的处理"""
        if self.state == "HALF_OPEN":
            self.state = "CLOSED"
            self.logger.info("Circuit breaker state: CLOSED")

        self.failure_count = 0

    def _on_failure(self) -> None:
        """失败时的处理"""
        self.failure_count += 1
        self.last_failure_time = datetime.now()

        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            self.logger.warning("Circuit breaker state: OPEN")


def circuit_breaker(
    failure_threshold: int = 5,
    recovery_timeout: int = 60,
    expected_exception: Type[Exception] = Exception,
):
    """熔断器装饰器"""
    breaker = CircuitBreaker(failure_threshold, recovery_timeout, expected_exception)

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            return breaker.call(func, *args, **kwargs)

        return wrapper

    return decorator


class RetryHandler:
    """重试处理器"""

    def __init__(
        self,
        max_retries: int = 3,
        delay: float = 1.0,
        backoff_factor: float = 2.0,
        exceptions: tuple = (Exception,),
    ):
        self.max_retries = max_retries
        self.delay = delay
        self.backoff_factor = backoff_factor
        self.exceptions = exceptions
        self.logger = logging.getLogger(f"{__name__}.RetryHandler")

    def execute(self, func: Callable, *args, **kwargs) -> Any:
        """执行带重试的函数"""
        import time

        last_exception = None
        current_delay = self.delay

        for attempt in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except self.exceptions as e:
                last_exception = e

                if attempt < self.max_retries:
                    self.logger.warning(
                        f"Attempt {attempt + 1} failed for {func.__name__}: {e}. "
                        f"Retrying in {current_delay}s..."
                    )
                    time.sleep(current_delay)
                    current_delay *= self.backoff_factor
                else:
                    self.logger.error(
                        (
                            f"All {self.max_retries + 1} attempts failed "
                            f"for {func.__name__}"
                        )
                    )

        raise last_exception


def retry(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,),
):
    """重试装饰器"""
    retry_handler = RetryHandler(max_retries, delay, backoff_factor, exceptions)

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            return retry_handler.execute(func, *args, **kwargs)

        return wrapper

    return decorator
