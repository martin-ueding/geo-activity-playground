import os

from django.core.asgi import get_asgi_application

"""
ASGI config for geo_activity_playground project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/asgi/
"""


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "geo_activity_playground.settings")

application = get_asgi_application()
