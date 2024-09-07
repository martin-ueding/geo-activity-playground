from flask import flash
from flask import session

from geo_activity_playground.core.config import Config


class Authenticator:
    def __init__(self, config: Config) -> None:
        self._config = config

    def is_authenticated(self) -> bool:
        return not self._config.upload_password or session.get(
            "is_authenticated", False
        )

    def authenticate(self, password: str) -> None:
        if password == self._config.upload_password:
            session["is_authenticated"] = True
            session.permanent = True
            flash("Login successful.", category="success")
        else:
            flash("Incorrect password.", category="danger")
