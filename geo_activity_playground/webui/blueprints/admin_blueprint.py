import logging
import os

from flask import Blueprint
from flask.typing import ResponseReturnValue

from ..authenticator import Authenticator, needs_authentication

logger = logging.getLogger(__name__)


def make_admin_blueprint(authenticator: Authenticator) -> Blueprint:
    blueprint = Blueprint("admin", __name__, template_folder="templates")

    @blueprint.route("/shutdown", methods=["POST"])
    @needs_authentication(authenticator)
    def shutdown() -> ResponseReturnValue:
        logger.info("Shutdown requested via web interface.")
        # Use os._exit to immediately terminate the process
        # This is appropriate here since we want a clean shutdown
        os._exit(0)

    return blueprint

