import logging
import os
import signal

from flask import Blueprint
from flask.typing import ResponseReturnValue

from ...webui.authenticator import Authenticator, needs_authentication

logger = logging.getLogger(__name__)


def make_shutdown_blueprint(
    authenticator: Authenticator, multi_process: bool = False
) -> Blueprint:
    blueprint = Blueprint("shutdown", __name__, template_folder="templates")

    @blueprint.route("/", methods=["POST"])
    @needs_authentication(authenticator)
    def shutdown() -> ResponseReturnValue:
        logger.info("Shutdown requested via web interface.")
        if multi_process:
            # We are a Gunicorn worker; os._exit(0) here would only kill this
            # worker and the master would respawn a replacement. Signal the
            # master (our parent process) instead, which stops all workers.
            os.kill(os.getppid(), signal.SIGTERM)
            return "", 204
        else:
            os._exit(0)

    return blueprint
