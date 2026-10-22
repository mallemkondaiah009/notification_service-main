import httpx
import base64
import logging

from django.conf import settings
from candidate.models import ConversationLog

logger = logging.getLogger("whatsapp.services")

# Reuse single httpx client across requests — much faster than creating per call
_http_client: httpx.AsyncClient | None = None


async def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=10.0)
    return _http_client


async def send_text_message(to_phone: str, message: str) -> None:
    """
    Raw async Twilio REST call.
    Raises httpx.HTTPStatusError on 4xx/5xx.
    """
    credentials = base64.b64encode(
        f"{settings.TWILIO_ACCOUNT_SID}:{settings.TWILIO_AUTH_TOKEN}".encode()
    ).decode()

    url = (
        f"https://api.twilio.com/2010-04-01/Accounts/"
        f"{settings.TWILIO_ACCOUNT_SID}/Messages.json"
    )

    client = await _get_http_client()

    response = await client.post(
        url,
        headers={"Authorization": f"Basic {credentials}"},
        data={
            "Body": message,
            "From": settings.TWILIO_WHATSAPP_NUMBER,
            "To":   f"whatsapp:{to_phone}",
        },
    )
    response.raise_for_status()
    logger.info("[SERVICES] Message sent — to=%s", to_phone)


async def send_whatsapp(candidate, message: str, is_initial: bool = False) -> None:
    """Send with optional initial ConversationLog entry."""
    try:
        await send_text_message(candidate.phone, message)

        if is_initial:
            await ConversationLog.alog(
                candidate=candidate,
                channel="whatsapp",
                direction="outbound",
                sender="system",
                message=message,
            )

    except Exception as exc:
        logger.error(
            "[SERVICES] send_whatsapp failed — candidate=%s error=%s",
            candidate.id, exc,
        )
        raise