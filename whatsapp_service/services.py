import httpx
import base64
import logging

from django.conf import settings
from candidate.models import Candidate, ConversationLog

logger = logging.getLogger("whatsapp.services")


async def send_text_message(to_phone: str, message: str) -> None:
    """Raw async Twilio REST call via httpx."""
    credentials = base64.b64encode(
        f"{settings.TWILIO_ACCOUNT_SID}:{settings.TWILIO_AUTH_TOKEN}".encode()
    ).decode()

    url = (
        f"https://api.twilio.com/2010-04-01/Accounts/"
        f"{settings.TWILIO_ACCOUNT_SID}/Messages.json"
    )

    async with httpx.AsyncClient(timeout=10.0) as client:
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


async def send_whatsapp(candidate: Candidate, message: str, is_initial: bool = False) -> None:
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

        logger.info("[WHATSAPP] Sent — candidate=%s is_initial=%s", candidate.id, is_initial)

    except Exception as exc:
        logger.error("[WHATSAPP] Failed — candidate=%s error=%s", candidate.id, exc)
        raise