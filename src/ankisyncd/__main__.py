import os
import sys
import signal
import atexit

import ankisyncd
from ankisyncd.config import load_from_file
from ankisyncd.config import load_from_env
from ankisyncd import logging
from ankisyncd.sync_app import SyncApp
from ankisyncd.server import run_server

logger = logging.get_logger("ankisyncd")

if __package__ is None and not hasattr(sys, "frozen"):
    path = os.path.realpath(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(path)))


def main():
    logger.info(
        "ankisyncd {} ({})".format(ankisyncd._get_version(), ankisyncd._homepage)
    )

    config = load_from_file(sys.argv)
    load_from_env(config)

    ankiserver = SyncApp(config)
    
    # Set up graceful shutdown handlers
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}. Initiating graceful shutdown...")
        if hasattr(ankiserver, 'collection_manager'):
            try:
                ankiserver.collection_manager.close_all()
                logger.info("All collections closed successfully")
            except Exception as e:
                logger.error(f"Error closing collections during shutdown: {e}")
        sys.exit(0)
    
    def cleanup_on_exit():
        logger.info("Performing cleanup on exit...")
        if hasattr(ankiserver, 'collection_manager'):
            try:
                ankiserver.collection_manager.close_all()
            except Exception as e:
                logger.error(f"Error during exit cleanup: {e}")
    
    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    atexit.register(cleanup_on_exit)
    
    try:
        run_server(ankiserver, config["host"], int(config["port"]))
    except KeyboardInterrupt:
        logger.info("Received KeyboardInterrupt. Shutting down gracefully...")
        signal_handler(signal.SIGINT, None)


if __name__ == "__main__":
    main()
