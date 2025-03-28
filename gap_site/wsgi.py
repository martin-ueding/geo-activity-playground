import os

from django.core.wsgi import get_wsgi_application

"""
WSGI config for gap_site project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/wsgi/
"""
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gap_site.settings")

application = get_wsgi_application()
