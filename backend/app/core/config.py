
import logging
from src.utils.config import setup_logging, get_config

# 配置日志
setup_logging()
logger = logging.getLogger(__name__)

# 获取配置
config = get_config()
