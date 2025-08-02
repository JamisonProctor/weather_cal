# logging_config.py

import logging
import os
from logging.handlers import RotatingFileHandler

def setup_logging(
    log_file_env_var="LOG_FILE", 
    default_log_file="data/weather_cal.log",
    default_level="INFO"
):
    log_file = os.getenv(log_file_env_var, default_log_file)
    log_level = os.getenv("LOG_LEVEL", default_level).upper()
    log_formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(process)d %(name)s: %(message)s'
    )

    # Ensure log directory exists
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    # File handler (with rotation)
    file_handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=2)
    file_handler.setLevel(log_level)
    file_handler.setFormatter(log_formatter)

    # Stream handler (console)
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(log_level)
    stream_handler.setFormatter(log_formatter)

    logger = logging.getLogger()
    logger.setLevel(log_level)
    # Remove all old handlers (prevents duplication in reload/dev)
    logger.handlers.clear()
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)