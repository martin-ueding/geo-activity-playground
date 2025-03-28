import os

from django.core.wsgi import get_wsgi_application

"""
WSGI config for geo_activity_playground project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/wsgi/
"""

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "geo_activity_playground.settings")

application = get_wsgi_application()
