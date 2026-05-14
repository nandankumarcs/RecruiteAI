import logging

logger = logging.getLogger("recruiteai.debug")

def log_debug(message: str) -> None:
    logger.debug(message)
