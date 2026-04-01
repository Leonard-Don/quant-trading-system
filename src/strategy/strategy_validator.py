"""
策略参数验证器
提供策略参数的验证和清理功能
"""

import logging
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ParameterRule:
    """参数验证规则"""

    name: str
    type: type
    default: Any
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    required: bool = False
    description: str = ""

    def validate(self, value: Any) -> Tuple[bool, Optional[str]]:
        """
        验证参数值

        Args:
            value: 要验证的值

        Returns:
            (是否有效, 错误消息)
        """
        # 检查类型
        if not isinstance(value, self.type):
            try:
                value = self.type(value)
            except (ValueError, TypeError):
                return False, f"参数 {self.name} 必须是 {self.type.__name__} 类型"

        # 检查范围
        if self.min_value is not None and value < self.min_value:
            return False, f"参数 {self.name} 不能小于 {self.min_value}"

        if self.max_value is not None and value > self.max_value:
            return False, f"参数 {self.name} 不能大于 {self.max_value}"

        return True, None


class StrategyValidator:
    """策略验证器"""

    # 策略参数规则定义
    STRATEGY_RULES: Dict[str, List[ParameterRule]] = {
        "moving_average": [
            ParameterRule(
                name="fast_period",
                type=int,
                default=20,
                min_value=2,
                max_value=100,
                required=True,
                description="快速移动平均周期",
            ),
            ParameterRule(
                name="slow_period",
                type=int,
                default=50,
                min_value=10,
                max_value=200,
                required=True,
                description="慢速移动平均周期",
            ),
        ],
        "rsi": [
            ParameterRule(
                name="period",
                type=int,
                default=14,
                min_value=5,
                max_value=50,
                required=True,
                description="RSI周期",
            ),
            ParameterRule(
                name="oversold",
                type=int,
                default=30,
                min_value=10,
                max_value=50,
                required=True,
                description="超卖阈值",
            ),
            ParameterRule(
                name="overbought",
                type=int,
                default=70,
                min_value=50,
                max_value=90,
                required=True,
                description="超买阈值",
            ),
        ],
        "bollinger_bands": [
            ParameterRule(
                name="period",
                type=int,
                default=20,
                min_value=10,
                max_value=50,
                required=True,
                description="布林带周期",
            ),
            ParameterRule(
                name="num_std",
                type=float,
                default=2.0,
                min_value=1.0,
                max_value=3.0,
                required=True,
                description="标准差倍数",
            ),
        ],
        "macd": [
            ParameterRule(
                name="fast_period",
                type=int,
                default=12,
                min_value=5,
                max_value=30,
                required=True,
                description="MACD快线周期",
            ),
            ParameterRule(
                name="slow_period",
                type=int,
                default=26,
                min_value=15,
                max_value=50,
                required=True,
                description="MACD慢线周期",
            ),
            ParameterRule(
                name="signal_period",
                type=int,
                default=9,
                min_value=5,
                max_value=20,
                required=True,
                description="MACD信号线周期",
            ),
        ],
        "mean_reversion": [
            ParameterRule(
                name="lookback_period",
                type=int,
                default=20,
                min_value=10,
                max_value=100,
                required=True,
                description="回看周期",
            ),
            ParameterRule(
                name="entry_threshold",
                type=float,
                default=2.0,
                min_value=1.0,
                max_value=4.0,
                required=True,
                description="入场Z-score阈值",
            ),
        ],
        "vwap": [
            ParameterRule(
                name="period",
                type=int,
                default=20,
                min_value=5,
                max_value=100,
                required=True,
                description="VWAP周期",
            ),
        ],
        "momentum": [
            ParameterRule(
                name="fast_window",
                type=int,
                default=10,
                min_value=5,
                max_value=50,
                required=True,
                description="快速窗口",
            ),
            ParameterRule(
                name="slow_window",
                type=int,
                default=30,
                min_value=15,
                max_value=100,
                required=True,
                description="慢速窗口",
            ),
        ],
        "stochastic": [
            ParameterRule(
                name="k_period",
                type=int,
                default=14,
                min_value=5,
                max_value=50,
                required=True,
                description="K 线周期",
            ),
            ParameterRule(
                name="d_period",
                type=int,
                default=3,
                min_value=2,
                max_value=20,
                required=True,
                description="D 线周期",
            ),
            ParameterRule(
                name="oversold",
                type=float,
                default=20,
                min_value=0,
                max_value=50,
                required=True,
                description="超卖阈值",
            ),
            ParameterRule(
                name="overbought",
                type=float,
                default=80,
                min_value=50,
                max_value=100,
                required=True,
                description="超买阈值",
            ),
        ],
        "atr_trailing_stop": [
            ParameterRule(
                name="atr_period",
                type=int,
                default=14,
                min_value=5,
                max_value=50,
                required=True,
                description="ATR 周期",
            ),
            ParameterRule(
                name="atr_multiplier",
                type=float,
                default=2.0,
                min_value=0.5,
                max_value=10.0,
                required=True,
                description="ATR 倍数",
            ),
        ],
        "turtle_trading": [
            ParameterRule(
                name="entry_period",
                type=int,
                default=20,
                min_value=5,
                max_value=120,
                required=True,
                description="突破入场周期",
            ),
            ParameterRule(
                name="exit_period",
                type=int,
                default=10,
                min_value=3,
                max_value=60,
                required=True,
                description="退出通道周期",
            ),
        ],
        "multi_factor": [
            ParameterRule(
                name="momentum_window",
                type=int,
                default=20,
                min_value=5,
                max_value=120,
                required=True,
                description="动量窗口",
            ),
            ParameterRule(
                name="mean_reversion_window",
                type=int,
                default=5,
                min_value=2,
                max_value=30,
                required=True,
                description="均值回归窗口",
            ),
            ParameterRule(
                name="volume_window",
                type=int,
                default=20,
                min_value=5,
                max_value=120,
                required=True,
                description="成交量窗口",
            ),
            ParameterRule(
                name="volatility_window",
                type=int,
                default=20,
                min_value=5,
                max_value=120,
                required=True,
                description="波动率窗口",
            ),
            ParameterRule(
                name="entry_threshold",
                type=float,
                default=0.4,
                min_value=0.05,
                max_value=3.0,
                required=True,
                description="入场阈值",
            ),
            ParameterRule(
                name="exit_threshold",
                type=float,
                default=0.1,
                min_value=0.0,
                max_value=1.5,
                required=True,
                description="离场阈值",
            ),
        ],
    }

    @classmethod
    def validate_strategy_params(
        cls, strategy_name: str, parameters: Dict[str, Any]
    ) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """
        验证策略参数

        Args:
            strategy_name: 策略名称
            parameters: 参数字典

        Returns:
            (是否有效, 错误消息, 清理后的参数)
        """
        # 检查策略是否存在
        if strategy_name not in cls.STRATEGY_RULES:
            if strategy_name == "buy_and_hold":
                # 买入持有策略没有参数
                return True, None, {}
            return False, f"未知策略: {strategy_name}", {}

        rules = cls.STRATEGY_RULES[strategy_name]
        cleaned_params = {}

        # 验证每个参数
        for rule in rules:
            value = parameters.get(rule.name)

            # 使用默认值如果参数未提供
            if value is None:
                if rule.required and rule.name not in parameters:
                    logger.info(f"使用默认值 {rule.name}={rule.default}")
                cleaned_params[rule.name] = rule.default
                continue

            # 验证参数
            is_valid, error_msg = rule.validate(value)
            if not is_valid:
                return False, error_msg, {}

            # 类型转换
            try:
                cleaned_params[rule.name] = rule.type(value)
            except (ValueError, TypeError) as e:
                return False, f"参数 {rule.name} 类型转换失败: {str(e)}", {}

        # 额外的逻辑验证
        validation_error = cls._validate_logic(strategy_name, cleaned_params)
        if validation_error:
            return False, validation_error, {}

        logger.info(f"策略参数验证通过: {strategy_name}, 参数: {cleaned_params}")
        return True, None, cleaned_params

    @classmethod
    def _validate_logic(
        cls, strategy_name: str, params: Dict[str, Any]
    ) -> Optional[str]:
        """
        验证参数的逻辑关系

        Args:
            strategy_name: 策略名称
            params: 参数字典

        Returns:
            错误消息，如果验证通过则返回None
        """
        if strategy_name == "moving_average":
            if params["fast_period"] >= params["slow_period"]:
                return "快速周期必须小于慢速周期"

        elif strategy_name == "rsi":
            if params["oversold"] >= params["overbought"]:
                return "超卖阈值必须小于超买阈值"

        elif strategy_name == "macd":
            if params["fast_period"] >= params["slow_period"]:
                return "MACD快线周期必须小于慢线周期"

        elif strategy_name == "momentum":
            if params["fast_window"] >= params["slow_window"]:
                return "快速窗口必须小于慢速窗口"

        elif strategy_name == "stochastic":
            if params["oversold"] >= params["overbought"]:
                return "超卖阈值必须小于超买阈值"
        elif strategy_name == "turtle_trading":
            if params["entry_period"] <= params["exit_period"]:
                return "突破入场周期必须大于退出通道周期"
        elif strategy_name == "multi_factor":
            if params["exit_threshold"] >= params["entry_threshold"]:
                return "离场阈值必须小于入场阈值"

        return None

    @classmethod
    def get_strategy_info(cls, strategy_name: str) -> Optional[Dict[str, Any]]:
        """
        获取策略信息

        Args:
            strategy_name: 策略名称

        Returns:
            策略信息字典
        """
        if strategy_name not in cls.STRATEGY_RULES:
            if strategy_name == "buy_and_hold":
                return {
                    "name": strategy_name,
                    "description": "买入持有策略",
                    "parameters": {},
                }
            return None

        rules = cls.STRATEGY_RULES[strategy_name]
        params_info = {}

        for rule in rules:
            params_info[rule.name] = {
                "type": rule.type.__name__,
                "default": rule.default,
                "min": rule.min_value,
                "max": rule.max_value,
                "required": rule.required,
                "description": rule.description,
            }

        return {"name": strategy_name, "parameters": params_info}

    @classmethod
    def get_all_strategies_info(cls) -> List[Dict[str, Any]]:
        """
        获取所有策略的信息

        Returns:
            策略信息列表
        """
        strategies = []

        # 添加所有已定义规则的策略
        for strategy_name in cls.STRATEGY_RULES.keys():
            info = cls.get_strategy_info(strategy_name)
            if info:
                strategies.append(info)

        # 添加买入持有策略
        strategies.append(cls.get_strategy_info("buy_and_hold"))

        return strategies
