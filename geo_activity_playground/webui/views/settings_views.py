from flask import Flask
from flask import render_template
from flask import request
from flask import Response

from geo_activity_playground.core.config import ConfigAccessor
from geo_activity_playground.webui.authenticator import Authenticator
from geo_activity_playground.webui.authenticator import needs_authentication
from geo_activity_playground.webui.flasher import Flasher
from geo_activity_playground.webui.flasher import FlashTypes
from geo_activity_playground.webui.interfaces import MyView


class SettingsAdminPasswordView(MyView):
    def __init__(
        self,
        authenticator: Authenticator,
        config_accessor: ConfigAccessor,
        flasher: Flasher,
    ) -> None:
        self._authenticator = authenticator
        self._config_accessor = config_accessor
        self._flasher = flasher

    def register(self, app: Flask) -> None:
        return app.add_url_rule(
            "/settings/admin-password",
            "settings.admin_password",
            needs_authentication(self._authenticator)(self.dispatch),
            methods=["GET", "POST"],
        )

    def dispatch(self) -> Response:
        if request.method == "POST":
            self._config_accessor().upload_password = request.form["password"]
            self._config_accessor.save()
            self._flasher.flash_message("Updated admin password.", FlashTypes.SUCCESS)
        return render_template(
            "settings/admin-password.html.j2",
            password=self._config_accessor().upload_password,
        )
