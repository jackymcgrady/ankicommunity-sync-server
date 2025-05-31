import logging as stdlib_logging


def get_logger(name: str):
    # Set up basic configuration
    stdlib_logging.basicConfig(
        level=stdlib_logging.INFO, format="[%(asctime)s]:%(levelname)s:%(name)s:%(message)s"
    )
    
    # Get the logger
    logger = stdlib_logging.getLogger(name)
    
    # Suppress specific verbose loggers while keeping sync operations visible
    if 'media_manager' in name:
        # Reduce media manager spam but keep errors
        logger.setLevel(stdlib_logging.WARNING)
    elif 'sync' in name or 'Sync' in name:
        # Keep sync operations visible
        logger.setLevel(stdlib_logging.INFO)
    
    return logger
