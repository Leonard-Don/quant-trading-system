"""
基础架构组件
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List
from datetime import datetime
import logging
from dataclasses import dataclass, field
import uuid


@dataclass
class ComponentConfig:
    """组件配置"""

    name: str
    version: str = "1.0.0"
    enabled: bool = True
    parameters: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


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
        self._dependencies = {}
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
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """清理资源"""
        pass

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

    def get_info(self) -> Dict[str, Any]:
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
        pass

    @abstractmethod
    async def stop(self) -> None:
        """停止服务"""
        pass

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        pass

    def is_running(self) -> bool:
        """检查服务是否运行中"""
        return self.running

    def get_uptime(self) -> Optional[float]:
        """获取运行时间（秒）"""
        if not self.start_time:
            return None

        end_time = self.stop_time or datetime.now()
        return (end_time - self.start_time).total_seconds()

    def get_service_info(self) -> Dict[str, Any]:
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


class Singleton(type):
    """单例元类"""

    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


class ConfigurableComponent(BaseComponent):
    """可配置组件基类"""

    def __init__(self, config: ComponentConfig):
        super().__init__(config)
        self._config_validators = {}
        self._config_transformers = {}

    def add_config_validator(self, key: str, validator: callable) -> None:
        """添加配置验证器"""
        self._config_validators[key] = validator

    def add_config_transformer(self, key: str, transformer: callable) -> None:
        """添加配置转换器"""
        self._config_transformers[key] = transformer

    def validate_config(self) -> bool:
        """验证配置"""
        for key, validator in self._config_validators.items():
            if key in self.config.parameters:
                value = self.config.parameters[key]
                if not validator(value):
                    self.logger.error(f"Config validation failed for {key}: {value}")
                    return False
        return True

    def transform_config(self) -> None:
        """转换配置"""
        for key, transformer in self._config_transformers.items():
            if key in self.config.parameters:
                self.config.parameters[key] = transformer(self.config.parameters[key])

    def get_config_value(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        return self.config.parameters.get(key, default)

    def set_config_value(self, key: str, value: Any) -> None:
        """设置配置值"""
        self.config.parameters[key] = value
        self.logger.debug(f"Config updated: {key} = {value}")


class LifecycleManager:
    """生命周期管理器"""

    def __init__(self):
        self.components: List[BaseComponent] = []
        self.logger = logging.getLogger(__name__)

    def register(self, component: BaseComponent) -> None:
        """注册组件"""
        self.components.append(component)
        self.logger.info(f"Registered component: {component.name}")

    def initialize_all(self) -> None:
        """初始化所有组件"""
        # 按依赖顺序排序
        sorted_components = self._topological_sort()

        for component in sorted_components:
            if component.is_enabled:
                try:
                    component.initialize()
                    component.status = "initialized"
                    self.logger.info(f"Initialized component: {component.name}")
                except Exception as e:
                    component.status = "error"
                    self.logger.error(f"Failed to initialize {component.name}: {e}")
                    raise

    def cleanup_all(self) -> None:
        """清理所有组件"""
        # 逆序清理
        for component in reversed(self.components):
            try:
                component.cleanup()
                component.status = "cleaned"
                self.logger.info(f"Cleaned up component: {component.name}")
            except Exception as e:
                self.logger.error(f"Failed to cleanup {component.name}: {e}")

    def _topological_sort(self) -> List[BaseComponent]:
        """拓扑排序，处理依赖关系"""
        # 简单的拓扑排序实现
        result = []
        visited = set()
        temp_visited = set()

        def visit(component: BaseComponent):
            if component.id in temp_visited:
                raise Exception(f"Circular dependency detected: {component.name}")

            if component.id not in visited:
                temp_visited.add(component.id)

                # 访问依赖
                for dep_name in component.config.dependencies:
                    dep_component = component.get_dependency(dep_name)
                    if dep_component:
                        visit(dep_component)

                temp_visited.remove(component.id)
                visited.add(component.id)
                result.append(component)

        for component in self.components:
            if component.id not in visited:
                visit(component)

        return result

    def get_component_status(self) -> Dict[str, Dict[str, Any]]:
        """获取所有组件状态"""
        return {component.name: component.get_info() for component in self.components}
