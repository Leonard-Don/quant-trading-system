"""
基础架构组件
"""

import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class ComponentConfig:
    """组件配置"""

    name: str
    version: str = "1.0.0"
    enabled: bool = True
    parameters: dict[str, Any] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseComponent(ABC):
    """基础组件类"""

    def __init__(self, config: ComponentConfig):
        self.config = config
        self.id = str(uuid.uuid4())
        self.logger = logging.getLogger(
            f"{self.__class__.__module__}.{self.__class__.__name__}"
        )
        self.created_at = datetime.now()
        self.status = "initialized"
        self._dependencies: dict[str, Any] = {}
        self._initialized = False

    @property
    def name(self) -> str:
        """组件名称"""
        return self.config.name

    @property
    def version(self) -> str:
        """组件版本"""
        return self.config.version

    @property
    def is_enabled(self) -> bool:
        """是否启用"""
        return self.config.enabled

    @abstractmethod
    def initialize(self) -> None:
        """初始化组件"""

    @abstractmethod
    def cleanup(self) -> None:
        """清理资源"""

    def add_dependency(self, name: str, component: "BaseComponent") -> None:
        """添加依赖组件"""
        self._dependencies[name] = component
        self.logger.debug(f"Added dependency: {name}")

    def get_dependency(self, name: str) -> Optional["BaseComponent"]:
        """获取依赖组件"""
        return self._dependencies.get(name)

    def validate_dependencies(self) -> bool:
        """验证依赖是否满足"""
        for dep_name in self.config.dependencies:
            if dep_name not in self._dependencies:
                self.logger.error(f"Missing dependency: {dep_name}")
                return False
        return True

    def get_info(self) -> dict[str, Any]:
        """获取组件信息"""
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "status": self.status,
            "enabled": self.is_enabled,
            "created_at": self.created_at.isoformat(),
            "dependencies": list(self._dependencies.keys()),
            "metadata": self.config.metadata,
        }

    def update_config(self, config: ComponentConfig) -> None:
        """更新配置"""
        old_config = self.config
        self.config = config
        self.logger.info(
            f"Config updated from version {old_config.version} to {config.version}"
        )

    def __str__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name}, version={self.version})"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self.id}, name={self.name})"


class BaseService(BaseComponent):
    """基础服务类"""

    def __init__(self, config: ComponentConfig):
        super().__init__(config)
        self.running = False
        self.start_time = None
        self.stop_time = None

    @abstractmethod
    async def start(self) -> None:
        """启动服务"""

    @abstractmethod
    async def stop(self) -> None:
        """停止服务"""

    @abstractmethod
    async def health_check(self) -> dict[str, Any]:
        """健康检查"""

    def is_running(self) -> bool:
        """检查服务是否运行中"""
        return self.running

    def get_uptime(self) -> Optional[float]:
        """获取运行时间（秒）"""
        if not self.start_time:
            return None

        end_time = self.stop_time or datetime.now()
        return (end_time - self.start_time).total_seconds()

    def get_service_info(self) -> dict[str, Any]:
        """获取服务信息"""
        info = self.get_info()
        info.update(
            {
                "running": self.running,
                "start_time": self.start_time.isoformat() if self.start_time else None,
                "stop_time": self.stop_time.isoformat() if self.stop_time else None,
                "uptime_seconds": self.get_uptime(),
            }
        )
        return info
