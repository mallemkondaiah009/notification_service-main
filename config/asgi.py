"""
ASGI config for config project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application
from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_asgi_application()

application = ASGIStaticFilesHandler(application)


async def application(scope, receive, send):
    if scope["type"] == "lifespan":
        while True:
            message = await receive()

            if message["type"] == "lifespan.startup":
                # Startup — nothing needed, pools init lazily
                await send({"type": "lifespan.startup.complete"})

            elif message["type"] == "lifespan.shutdown":
                # Shutdown — close psycopg3 pool cleanly
                try:
                    from django.db import connections
                    for conn in connections.all():
                        await conn.aclose()
                except Exception:
                    pass

                # Close async Redis connections
                try:
                    from shared.redis_client import redis_context
                    await redis_context.aclose()
                except Exception:
                    pass

                await send({"type": "lifespan.shutdown.complete"})
                return
    else:
        await django_app(scope, receive, send)