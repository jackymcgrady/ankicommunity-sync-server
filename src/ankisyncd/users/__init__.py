# -*- coding: utf-8 -*-

import importlib
import inspect

from ankisyncd import logging
from ankisyncd.users.simple_manager import SimpleUserManager
from ankisyncd.users.sqlite_manager import SqliteUserManager
from ankisyncd.users.cognito_manager import CognitoUserManager

logger = logging.get_logger(__name__)


def get_user_manager(config):
    # Check for Cognito configuration first
    if "cognito_user_pool_id" in config and config["cognito_user_pool_id"]:
        logger.info("Found cognito_user_pool_id in config, using CognitoUserManager for auth")
        cognito_config = {
            'user_pool_id': config.get("cognito_user_pool_id"),
            'client_id': config.get("cognito_client_id"),
            'region': config.get("cognito_region", "ap-southeast-1")
        }
        return CognitoUserManager(config)
    elif "auth_db_path" in config and config["auth_db_path"]:
        logger.info("Found auth_db_path in config, using SqliteUserManager for auth")
        return SqliteUserManager(config["auth_db_path"], config["data_root"])
    elif "user_manager" in config and config["user_manager"]:  # load from config
        logger.info(
            "Found user_manager in config, using {} for auth".format(
                config["user_manager"]
            )
        )

        module_name, class_name = config["user_manager"].rsplit(".", 1)
        module = importlib.import_module(module_name.strip())
        class_ = getattr(module, class_name.strip())

        if not SimpleUserManager in inspect.getmro(class_):
            raise TypeError(
                """"user_manager" found in the conf file but it doesn''t
                            inherit from SimpleUserManager"""
            )
        return class_(config)
    else:
        logger.warning(
            "No authentication configuration found (auth_db_path, cognito_user_pool_id, or user_manager), ankisyncd will accept any password"
        )
        return SimpleUserManager()
