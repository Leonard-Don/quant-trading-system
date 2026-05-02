
import logging

from src.utils.config import APP_VERSION as APP_VERSION, get_config, setup_logging

# 配置日志
setup_logging()
logger = logging.getLogger(__name__)

# 获取配置
config = get_config()
