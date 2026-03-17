import logging

from adrf.decorators import api_view           # ← async DRF
from rest_framework.request import Request
from rest_framework.response import Response

from candidate.models import Candidate, ConversationLog
from shared.jd_parser import extract_answer, FRIENDLY_LABELS

from .ai import get_ai_whatsapp_response
from .menus import (
    send_main_menu, send_salary_menu, send_responsibilities_menu,
    send_location_menu, send_notice_period_menu, send_benefits_menu,
    send_interest_buttons,
)
from .quick_replies import (
    resolve_intent, get_context, set_context, clear_context, JD_FIELDS,
)
from workers.tasks import send_bulk_whatsapp_notifications
from workers.tasks import send_whatsapp_reply_task

logger = logging.getLogger("whatsapp.views")


# ── Helpers ────────────────────────────────────────────────────────────

async def _log(candidate, direction, sender, message, status=None):
    await ConversationLog.alog(
        candidate=candidate,
        channel="whatsapp",
        direction=direction,
        sender=sender,
        message=message,
        ai_detected_status=status,
    )


async def _serve_jd_answer(candidate, field: str) -> None:
    label, answer = extract_answer(field, candidate.job_description)

    if answer:
        msg = f"*{label}*\n\n{answer}"
    else:
        label = FRIENDLY_LABELS.get(field, field.replace("_", " ").title())
        msg   = (
            f"We don't have specific details about *{label}* right now.\n\n"
            f"Feel free to type your question and our team will get back to you!"
        )

    await _log(candidate, "outbound", "system", msg)
    await send_interest_buttons(candidate, msg)


# ── Webhook ────────────────────────────────────────────────────────────

@api_view(["POST"])
async def whatsapp_webhook(request: Request) -> Response:
    phone   = request.data.get("From", "").replace("whatsapp:", "").strip()
    message = request.data.get("Body", "").strip()

    if not phone or not message:
        return Response({"status": "bad request"}, status=400)

    # ── Fetch candidate ────────────────────────────────────────────────
    try:
        candidate = await Candidate.aget_by_phone(phone)
    except Candidate.DoesNotExist:
        logger.warning("[WEBHOOK] Unknown phone — %s", phone)
        return Response({"status": "candidate not found"}, status=404)

    # ── Log inbound ────────────────────────────────────────────────────
    await _log(candidate, "inbound", "candidate", message)

    # ── Resolve intent (async — reads Redis context) ───────────────────
    intent = await resolve_intent(candidate.id, message)

    # ── Unrecognised inside a sub-menu → back to main ──────────────────
    if intent is None:
        ctx = await get_context(candidate.id)
        if ctx != "main":
            await clear_context(candidate.id)
            await send_main_menu(candidate)
        else:
            # Top-level unrecognised → AI fallback
            ai_reply, detected = await get_ai_whatsapp_response(
                candidate_message=message,
                candidate_name=candidate.full_name,
                role_name=candidate.role_name,
                job_description=candidate.job_description,
            )
            if detected == "interested":
                await candidate.amark_response("interested", "whatsapp")
                await clear_context(candidate.id)
            elif detected == "not_interested":
                await candidate.amark_response("not_interested", "whatsapp")
                await clear_context(candidate.id)

            await _log(candidate, "outbound", "ai", ai_reply, detected)
            send_whatsapp_reply_task.delay(candidate.id, ai_reply)

        return Response({"status": "received"})

    # ── TIER 1: Interested ─────────────────────────────────────────────
    if intent == "interested":
        await candidate.amark_response("interested", "whatsapp")
        await clear_context(candidate.id)
        reply = (
            f"Thank you for your interest, {candidate.full_name}! 😊\n\n"
            f"Our recruitment team will reach out to you very soon "
            f"with the next steps.\n\nHave a great day!"
        )
        await _log(candidate, "outbound", "system", reply, "interested")
        send_whatsapp_reply_task.delay(candidate.id, reply)

    # ── TIER 1: Not interested ─────────────────────────────────────────
    elif intent == "not_interested":
        await candidate.amark_response("not_interested", "whatsapp")
        await clear_context(candidate.id)
        reply = (
            f"Thank you for letting us know, {candidate.full_name}.\n\n"
            f"We will keep your profile on file for future opportunities.\n\n"
            f"All the best! 👍"
        )
        await _log(candidate, "outbound", "system", reply, "not_interested")
        send_whatsapp_reply_task.delay(candidate.id, reply)

    # ── TIER 1: Back to main ───────────────────────────────────────────
    elif intent == "back_main":
        await clear_context(candidate.id)
        await send_main_menu(candidate)

    # ── Menu navigation ────────────────────────────────────────────────
    elif intent == "menu_salary":
        await set_context(candidate.id, "salary")
        await send_salary_menu(candidate)

    elif intent == "menu_responsibilities":
        await set_context(candidate.id, "responsibilities")
        await send_responsibilities_menu(candidate)

    elif intent == "menu_location":
        await set_context(candidate.id, "location")
        await send_location_menu(candidate)

    elif intent == "menu_notice_period":
        await set_context(candidate.id, "notice_period")
        await send_notice_period_menu(candidate)

    elif intent == "menu_benefits":
        await set_context(candidate.id, "benefits")
        await send_benefits_menu(candidate)

    # ── TIER 2: Natural language JD topic ─────────────────────────────
    elif intent.startswith("jd_"):
        await _serve_jd_answer(candidate, intent[3:])

    # ── Numbered sub-menu JD fields ────────────────────────────────────
    elif intent in JD_FIELDS:
        await _serve_jd_answer(candidate, intent)

    return Response({"status": "received"})