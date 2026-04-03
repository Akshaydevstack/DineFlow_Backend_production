"""
ASGI config for notification_service project.
"""

import os
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.core.asgi import get_asgi_application

import notification_service.routing   

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "notification_service.settings")

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter({
    # HTTP requests (REST APIs)
    "http": django_asgi_app,

    # WebSocket requests
    "websocket": AuthMiddlewareStack(
        URLRouter(
            notification_service.routing.websocket_urlpatterns
        )
    ),
})