"""
The Main Script for Adding the Logger Module into any other
Script in the Project.

Created On: 24 Dec 2025
"""

import os
import sys
import logging

import config


def get_logger(name: str):
    """
    Creating, Adding, and Returning the Logger of the Project.

    Returns:
    --------
    logger: logging.Logger
        the logger object
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Check if handlers are already added to prevent duplicates
    if logger.handlers:
        return logger

    def get_path(file_name):
        return os.path.join(config.LOGGER["path"], file_name)

    os.makedirs(config.LOGGER["path"], exist_ok=True)

    # Create file handlers for each log level with a specific level
    handlers = {
        "info": logging.FileHandler(get_path("info.log")),
        "error": logging.FileHandler(get_path("error.log")),
        "debug": logging.StreamHandler(sys.stdout),  # print to console
    }

    # Create formatter and add to handlers
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    for handler in handlers.values():
        handler.setFormatter(formatter)

    # Create level filters
    class LevelFilter(logging.Filter):
        """Filter Logging Messages by Levels"""

        def __init__(self, level):
            super().__init__()
            self.level = level

        def filter(self, record):
            return record.levelno == self.level

    filters = {"info": LevelFilter(logging.INFO), "error": LevelFilter(logging.ERROR)}

    handlers["info"].addFilter(filters["info"])
    handlers["error"].addFilter(filters["error"])

    # Add Handlers to Logger
    for handler in handlers.values():
        logger.addHandler(handler)

    return logger
