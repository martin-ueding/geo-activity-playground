import abc

from flask import Flask


class MyView(abc.ABC):
    @abc.abstractmethod
    def register(self, app: Flask) -> None:
        pass
