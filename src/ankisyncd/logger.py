import logging as stdlib_logging


def get_logger(name: str):
    stdlib_logging.basicConfig(
        level=stdlib_logging.INFO, format="[%(asctime)s]:%(levelname)s:%(name)s:%(message)s"
    )
    return stdlib_logging.getLogger(name)
