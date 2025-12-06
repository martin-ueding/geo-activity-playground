import os
import logging

from flask import Blueprint
from flask import render_template
from flask.typing import ResponseReturnValue

from ..authenticator import Authenticator
from ..authenticator import needs_authentication


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

