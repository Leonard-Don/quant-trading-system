"""
事件系统模块
"""

import asyncio
from typing import Any, Callable, Dict, List, Optional, Type
from dataclasses import dataclass, field
from datetime import datetime
import logging
from collections import defaultdict
import weakref
import threading
from abc import ABC, abstractmethod


@dataclass
class Event:
    """事件基类"""

    name: str
    timestamp: datetime = field(default_factory=datetime.now)
    data: Dict[str, Any] = field(default_factory=dict)
    source: Optional[str] = None
    correlation_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
            "source": self.source,
            "correlation_id": self.correlation_id,
        }


class EventHandler(ABC):
    """事件处理器基类"""

    @abstractmethod
    async def handle(self, event: Event) -> None:
        """处理事件"""
        pass

    @property
    @abstractmethod
    def event_types(self) -> List[str]:
        """支持的事件类型"""
        pass

    @property
    def priority(self) -> int:
        """处理优先级，数字越小优先级越高"""
        return 100


class FunctionEventHandler(EventHandler):
    """函数式事件处理器"""

    def __init__(self, func: Callable, event_types: List[str], priority: int = 100):
        self._func = func
        self._event_types = event_types
        self._priority = priority

    async def handle(self, event: Event) -> None:
        """处理事件"""
        if asyncio.iscoroutinefunction(self._func):
            await self._func(event)
        else:
            self._func(event)

    @property
    def event_types(self) -> List[str]:
        return self._event_types

    @property
    def priority(self) -> int:
        return self._priority


class EventBus:
    """事件总线"""

    def __init__(self):
        self._handlers: Dict[str, List[EventHandler]] = defaultdict(list)
        self._global_handlers: List[EventHandler] = []
        self._event_history: List[Event] = []
        self._max_history = 1000
        self._lock = threading.RLock()
        self.logger = logging.getLogger(__name__)
        self._stats = {"events_published": 0, "events_handled": 0, "handler_errors": 0}

    def subscribe(self, handler: EventHandler) -> None:
        """订阅事件"""
        with self._lock:
            for event_type in handler.event_types:
                if event_type == "*":
                    self._global_handlers.append(handler)
                else:
                    self._handlers[event_type].append(handler)
                    # 按优先级排序
                    self._handlers[event_type].sort(key=lambda h: h.priority)

            self.logger.info(f"Subscribed handler for events: {handler.event_types}")

    def unsubscribe(self, handler: EventHandler) -> None:
        """取消订阅"""
        with self._lock:
            for event_type in handler.event_types:
                if event_type == "*":
                    if handler in self._global_handlers:
                        self._global_handlers.remove(handler)
                else:
                    if handler in self._handlers[event_type]:
                        self._handlers[event_type].remove(handler)

            self.logger.info(f"Unsubscribed handler for events: {handler.event_types}")

    def subscribe_function(
        self, func: Callable, event_types: List[str], priority: int = 100
    ) -> EventHandler:
        """订阅函数"""
        handler = FunctionEventHandler(func, event_types, priority)
        self.subscribe(handler)
        return handler

    async def publish(self, event: Event) -> None:
        """发布事件"""
        with self._lock:
            self._stats["events_published"] += 1

            # 添加到历史记录
            self._event_history.append(event)
            if len(self._event_history) > self._max_history:
                self._event_history.pop(0)

            # 获取处理器
            handlers = []

            # 全局处理器
            handlers.extend(self._global_handlers)

            # 特定事件类型处理器
            if event.name in self._handlers:
                handlers.extend(self._handlers[event.name])

            # 按优先级排序
            handlers.sort(key=lambda h: h.priority)

        self.logger.debug(f"Publishing event: {event.name} to {len(handlers)} handlers")

        # 并行处理事件
        if handlers:
            await self._handle_event_parallel(event, handlers)

    async def _handle_event_parallel(
        self, event: Event, handlers: List[EventHandler]
    ) -> None:
        """并行处理事件"""
        tasks = []

        for handler in handlers:
            task = asyncio.create_task(self._safe_handle_event(event, handler))
            tasks.append(task)

        # 等待所有处理器完成
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 统计结果
        for result in results:
            if isinstance(result, Exception):
                self._stats["handler_errors"] += 1
                self.logger.error(f"Event handler error: {result}")
            else:
                self._stats["events_handled"] += 1

    async def _safe_handle_event(self, event: Event, handler: EventHandler) -> None:
        """安全处理事件"""
        try:
            await handler.handle(event)
        except Exception as e:
            self.logger.error(
                f"Error in event handler {handler.__class__.__name__}: {e}"
            )
            raise

    def publish_sync(self, event: Event) -> None:
        """同步发布事件"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果在异步上下文中，创建任务
                asyncio.create_task(self.publish(event))
            else:
                # 如果不在异步上下文中，运行到完成
                loop.run_until_complete(self.publish(event))
        except RuntimeError:
            # 没有事件循环，创建新的
            asyncio.run(self.publish(event))

    def get_event_history(
        self, event_type: Optional[str] = None, limit: int = 100
    ) -> List[Event]:
        """获取事件历史"""
        with self._lock:
            history = self._event_history.copy()

            if event_type:
                history = [e for e in history if e.name == event_type]

            return history[-limit:]

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return {
                **self._stats.copy(),
                "active_handlers": sum(
                    len(handlers) for handlers in self._handlers.values()
                ),
                "global_handlers": len(self._global_handlers),
                "event_types": list(self._handlers.keys()),
                "history_size": len(self._event_history),
            }

    def clear_history(self) -> None:
        """清空事件历史"""
        with self._lock:
            self._event_history.clear()

    def reset_stats(self) -> None:
        """重置统计信息"""
        with self._lock:
            self._stats = {
                "events_published": 0,
                "events_handled": 0,
                "handler_errors": 0,
            }


# 预定义事件类型
class SystemEvent(Event):
    """系统事件"""

    pass


class StrategyEvent(Event):
    """策略事件"""

    pass


class BacktestEvent(Event):
    """回测事件"""

    pass


class DataEvent(Event):
    """数据事件"""

    pass


class ErrorEvent(Event):
    """错误事件"""

    pass


# 全局事件总线实例
event_bus = EventBus()


def on_event(event_types: List[str], priority: int = 100):
    """事件处理装饰器"""

    def decorator(func: Callable) -> Callable:
        event_bus.subscribe_function(func, event_types, priority)
        return func

    return decorator


async def emit_event(
    name: str, data: Dict[str, Any] = None, source: str = None
) -> None:
    """发射事件的便捷函数"""
    event = Event(name=name, data=data or {}, source=source)
    await event_bus.publish(event)


def emit_event_sync(name: str, data: Dict[str, Any] = None, source: str = None) -> None:
    """同步发射事件的便捷函数"""
    event = Event(name=name, data=data or {}, source=source)
    event_bus.publish_sync(event)
