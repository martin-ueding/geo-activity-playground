import abc
from enum import Enum

import flask


class FlashTypes(Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    SUCCESS = "success"
    DANGER = "danger"
    WARNING = "warning"
    INFO = "info"
    LIGHT = "light"
    DARK = "dark"


class Flasher(abc.ABC):
    @abc.abstractmethod
    def flash_message(self, message: str, type: FlashTypes):
        pass


class FlaskFlasher(Flasher):
    def flash_message(self, message, type):
        flask.flash(message, category=type.value)
