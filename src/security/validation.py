"""
安全验证模块
"""

import re
import html
import json
from typing import Any, Dict, List, Optional, Union, Callable
from datetime import datetime, timedelta
import hashlib
import secrets
import logging
from dataclasses import dataclass
from enum import Enum

from ..utils.exceptions import ValidationError


class SecurityLevel(Enum):
    """安全级别"""

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class ValidationRule:
    """验证规则"""

    name: str
    validator: Callable[[Any], bool]
    error_message: str
    security_level: SecurityLevel = SecurityLevel.MEDIUM


class InputSanitizer:
    """输入清理器"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        # 危险字符模式
        self.sql_injection_patterns = [
            r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC)\b)",
            r"(;|\|\||&&|--|\#|\*|/\*|\*/)",
            r"(\bunion\b|\bor\b|\band\b)",
            r"(\'|\"|`|\\)",
        ]

        self.xss_patterns = [
            r"<script[^>]*>.*?</script>",
            r"javascript:",
            r"vbscript:",
            r"onload=",
            r"onerror=",
            r"onclick=",
            r"<iframe[^>]*>.*?</iframe>",
        ]

        self.command_injection_patterns = [
            r"(\||;|&|`|\$\(|\${)",
            r"(\.\./|\.\.\\)",
            r"(rm\s|del\s|format\s)",
            r"(wget|curl|nc|netcat)",
        ]

    def sanitize_string(self, value: str, max_length: int = 1000) -> str:
        """清理字符串输入"""
        if not isinstance(value, str):
            raise ValidationError("Value must be a string")

        # 长度检查
        if len(value) > max_length:
            raise ValidationError(f"String too long (max: {max_length})")

        # HTML转义
        sanitized = html.escape(value)

        # 移除控制字符
        sanitized = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", sanitized)

        return sanitized.strip()

    def sanitize_number(
        self,
        value: Union[int, float, str],
        min_val: float = None,
        max_val: float = None,
    ) -> Union[int, float]:
        """清理数字输入"""
        try:
            if isinstance(value, str):
                # 移除非数字字符
                cleaned = re.sub(r"[^0-9.-]", "", value)
                if "." in cleaned:
                    num_value = float(cleaned)
                else:
                    num_value = int(cleaned)
            else:
                num_value = value

            # 范围检查
            if min_val is not None and num_value < min_val:
                raise ValidationError(f"Value too small (min: {min_val})")

            if max_val is not None and num_value > max_val:
                raise ValidationError(f"Value too large (max: {max_val})")

            return num_value

        except (ValueError, TypeError):
            raise ValidationError("Invalid number format")

    def check_sql_injection(self, value: str) -> bool:
        """检查SQL注入"""
        value_lower = value.lower()

        for pattern in self.sql_injection_patterns:
            if re.search(pattern, value_lower, re.IGNORECASE):
                self.logger.warning(f"Potential SQL injection detected: {pattern}")
                return True

        return False

    def check_xss(self, value: str) -> bool:
        """检查XSS攻击"""
        value_lower = value.lower()

        for pattern in self.xss_patterns:
            if re.search(pattern, value_lower, re.IGNORECASE):
                self.logger.warning(f"Potential XSS detected: {pattern}")
                return True

        return False

    def check_command_injection(self, value: str) -> bool:
        """检查命令注入"""
        for pattern in self.command_injection_patterns:
            if re.search(pattern, value, re.IGNORECASE):
                self.logger.warning(f"Potential command injection detected: {pattern}")
                return True

        return False

    def validate_email(self, email: str) -> bool:
        """验证邮箱格式"""
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        return bool(re.match(pattern, email))

    def validate_ip_address(self, ip: str) -> bool:
        """验证IP地址格式"""
        # IPv4 pattern
        ipv4_pattern = r"^(\d{1,3}\.){3}\d{1,3}$"
        if re.match(ipv4_pattern, ip):
            parts = ip.split(".")
            return all(0 <= int(part) <= 255 for part in parts)

        # IPv6 pattern (简化版)
        ipv6_pattern = r"^([0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}$"
        return bool(re.match(ipv6_pattern, ip))

    def sanitize_filename(self, filename: str) -> str:
        """清理文件名"""
        # 移除危险字符
        sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", filename)

        # 移除保留名称
        reserved_names = [
            "CON",
            "PRN",
            "AUX",
            "NUL",
            "COM1",
            "COM2",
            "COM3",
            "COM4",
            "COM5",
            "COM6",
            "COM7",
            "COM8",
            "COM9",
            "LPT1",
            "LPT2",
            "LPT3",
            "LPT4",
            "LPT5",
            "LPT6",
            "LPT7",
            "LPT8",
            "LPT9",
        ]

        name_part = sanitized.split(".")[0].upper()
        if name_part in reserved_names:
            sanitized = f"safe_{sanitized}"

        # 限制长度
        if len(sanitized) > 255:
            name, ext = (
                sanitized.rsplit(".", 1) if "." in sanitized else (sanitized, "")
            )
            sanitized = name[:250] + ("." + ext if ext else "")

        return sanitized


class SecurityValidator:
    """安全验证器"""

    def __init__(self):
        self.sanitizer = InputSanitizer()
        self.logger = logging.getLogger(__name__)
        self.validation_rules: Dict[str, List[ValidationRule]] = {}
        self.blocked_ips: set = set()
        self.suspicious_activities: Dict[str, List[datetime]] = {}

        # 默认验证规则
        self._setup_default_rules()

    def _setup_default_rules(self):
        """设置默认验证规则"""
        # 字符串验证规则
        self.add_rule(
            "string",
            ValidationRule(
                name="no_sql_injection",
                validator=lambda x: not self.sanitizer.check_sql_injection(str(x)),
                error_message="Potential SQL injection detected",
                security_level=SecurityLevel.HIGH,
            ),
        )

        self.add_rule(
            "string",
            ValidationRule(
                name="no_xss",
                validator=lambda x: not self.sanitizer.check_xss(str(x)),
                error_message="Potential XSS attack detected",
                security_level=SecurityLevel.HIGH,
            ),
        )

        # 数字验证规则
        self.add_rule(
            "number",
            ValidationRule(
                name="positive",
                validator=lambda x: float(x) >= 0,
                error_message="Value must be non-negative",
                security_level=SecurityLevel.LOW,
            ),
        )

    def add_rule(self, field_type: str, rule: ValidationRule):
        """添加验证规则"""
        if field_type not in self.validation_rules:
            self.validation_rules[field_type] = []

        self.validation_rules[field_type].append(rule)
        self.logger.debug(f"Added validation rule: {rule.name} for {field_type}")

    def validate_field(
        self, field_type: str, value: Any, custom_rules: List[ValidationRule] = None
    ) -> bool:
        """验证字段"""
        rules = self.validation_rules.get(field_type, [])

        if custom_rules:
            rules.extend(custom_rules)

        for rule in rules:
            try:
                if not rule.validator(value):
                    self.logger.warning(f"Validation failed: {rule.error_message}")

                    if rule.security_level == SecurityLevel.CRITICAL:
                        self._record_suspicious_activity("critical_validation_failure")

                    raise ValidationError(rule.error_message)

            except Exception as e:
                if isinstance(e, ValidationError):
                    raise
                else:
                    self.logger.error(f"Validation rule error: {e}")
                    raise ValidationError(f"Validation error: {rule.name}")

        return True

    def validate_request_data(
        self, data: Dict[str, Any], schema: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """验证请求数据"""
        validated_data = {}

        for field_name, field_config in schema.items():
            if field_name not in data:
                if field_config.get("required", False):
                    raise ValidationError(f"Required field missing: {field_name}")
                else:
                    continue

            value = data[field_name]
            field_type = field_config.get("type", "string")

            # 类型转换和清理
            if field_type == "string":
                max_length = field_config.get("max_length", 1000)
                value = self.sanitizer.sanitize_string(value, max_length)
            elif field_type == "number":
                min_val = field_config.get("min")
                max_val = field_config.get("max")
                value = self.sanitizer.sanitize_number(value, min_val, max_val)
            elif field_type == "email":
                value = self.sanitizer.sanitize_string(value)
                if not self.sanitizer.validate_email(value):
                    raise ValidationError(f"Invalid email format: {field_name}")

            # 应用验证规则
            custom_rules = field_config.get("rules", [])
            self.validate_field(field_type, value, custom_rules)

            validated_data[field_name] = value

        return validated_data

    def check_rate_limit(
        self, identifier: str, max_requests: int = 100, window_minutes: int = 60
    ) -> bool:
        """检查速率限制"""
        now = datetime.now()
        window_start = now - timedelta(minutes=window_minutes)

        if identifier not in self.suspicious_activities:
            self.suspicious_activities[identifier] = []

        # 清理过期记录
        self.suspicious_activities[identifier] = [
            timestamp
            for timestamp in self.suspicious_activities[identifier]
            if timestamp > window_start
        ]

        # 检查是否超过限制
        if len(self.suspicious_activities[identifier]) >= max_requests:
            self.logger.warning(f"Rate limit exceeded for {identifier}")
            return False

        # 记录当前请求
        self.suspicious_activities[identifier].append(now)
        return True

    def _record_suspicious_activity(
        self, activity_type: str, identifier: str = "unknown"
    ):
        """记录可疑活动"""
        self.logger.warning(f"Suspicious activity: {activity_type} from {identifier}")

        # 可以在这里添加更多的安全响应逻辑
        # 例如：自动封禁IP、发送警报等

    def block_ip(self, ip_address: str, reason: str = "Security violation"):
        """封禁IP地址"""
        self.blocked_ips.add(ip_address)
        self.logger.warning(f"Blocked IP {ip_address}: {reason}")

    def is_ip_blocked(self, ip_address: str) -> bool:
        """检查IP是否被封禁"""
        return ip_address in self.blocked_ips

    def unblock_ip(self, ip_address: str):
        """解除IP封禁"""
        self.blocked_ips.discard(ip_address)
        self.logger.info(f"Unblocked IP {ip_address}")

    def get_security_report(self) -> Dict[str, Any]:
        """获取安全报告"""
        return {
            "timestamp": datetime.now().isoformat(),
            "blocked_ips": list(self.blocked_ips),
            "suspicious_activities_count": len(self.suspicious_activities),
            "validation_rules_count": sum(
                len(rules) for rules in self.validation_rules.values()
            ),
            "active_monitoring": True,
        }


# 全局安全验证器实例
security_validator = SecurityValidator()
input_sanitizer = InputSanitizer()


def validate_input(field_type: str, custom_rules: List[ValidationRule] = None):
    """输入验证装饰器"""

    def decorator(func):
        def wrapper(*args, **kwargs):
            # 验证参数
            for i, arg in enumerate(args):
                security_validator.validate_field(field_type, arg, custom_rules)

            for key, value in kwargs.items():
                security_validator.validate_field(field_type, value, custom_rules)

            return func(*args, **kwargs)

        return wrapper

    return decorator


def sanitize_output(func):
    """输出清理装饰器"""

    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)

        if isinstance(result, str):
            return input_sanitizer.sanitize_string(result)
        elif isinstance(result, dict):
            return {
                k: input_sanitizer.sanitize_string(v) if isinstance(v, str) else v
                for k, v in result.items()
            }
        elif isinstance(result, list):
            return [
                input_sanitizer.sanitize_string(item) if isinstance(item, str) else item
                for item in result
            ]

        return result

    return wrapper
