import logging
import logging.handlers

logger = logging.getLogger(__name__)
handler = logging.handlers.RotatingFileHandler('test.log')
