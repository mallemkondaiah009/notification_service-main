import asyncio
import logging

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from adrf.views import APIView
from rest_framework.request import Request
from rest_framework.response import Response

from candidate.models import Candidate, ConversationLog
from shared.jd_parser import (
    extract_answer,
    get_cached_answer,
    FRIENDLY_LABELS,
    clean_for_whatsapp,
)

from .ai import get_ai_whatsapp_response
from .menu_text import (
    main_menu_text,
    SALARY_MENU,
    RESPONSIBILITIES_MENU,
    LOCATION_MENU,
    NOTICE_MENU,
    BENEFITS_MENU,
)
from .quick_replies import (
    resolve_intent, get_context, set_context, clear_context,
    JD_FIELDS, JD_QUESTION_INTENTS,
)

logger = logging.getLogger("whatsapp.views")

# ── Cached task reference — imported once, reused forever ─────────────
_reply_task = None

def _get_reply_task():
    global _reply_task
    if _reply_task is None:
        from workers.tasks import send_whatsapp_reply_task
        _reply_task = send_whatsapp_reply_task
    return _reply_task


# ── Internal helpers ───────────────────────────────────────────────────

async def _log(
    candidate,
    direction: str,
    sender: str,
    message: str,
    status: str | None = None,
) -> None:
    if direction == "outbound" and status == "unclear":
        if candidate.status in ("interested", "not_interested"):
            status = candidate.status

    await ConversationLog.alog(
        candidate=candidate,
        channel="whatsapp",
        direction=direction,
        sender=sender,
        message=message,
        ai_detected_status=status,
    )


async def _warm_jd_cache(jd_id: int, job_content: str) -> None:
    """
    Background cache warm — fire and forget.
    Never blocks the reply path.
    """
    from shared.jd_parser import cache_jd_answers
    try:
        await cache_jd_answers(jd_id, job_content)
        logger.info("[VIEWS] Cache warmed — jd_id=%d", jd_id)
    except Exception as exc:
        logger.error("[VIEWS] Cache warm failed — jd_id=%d error=%s", jd_id, exc)


async def _serve_jd_answer(candidate, field: str) -> None:
    """
    Serve JD answer.
    Cache hit  → instant reply
    Cache miss → live scan + background cache warm (non-blocking)
    """
    label, answer = await get_cached_answer(candidate.job.id, field)

    if not answer:
        logger.info(
            "[VIEWS] Cache miss — jd_id=%d field=%s — live scan",
            candidate.job.id, field,
        )
        label, answer = extract_answer(field, candidate.job.content)
        if answer:
            answer = clean_for_whatsapp(answer)

        # Warm cache in background — does not block reply
        asyncio.ensure_future(_warm_jd_cache(candidate.job.id, candidate.job.content))

    if answer:
        msg = f"*{label}*\n\n{answer}"
    else:
        label = FRIENDLY_LABELS.get(field, field.replace("_", " ").title())
        msg = (
            f"We don't have specific details about *{label}* right now.\n\n"
            f"Feel free to type your question and our team will get back to you!"
        )

    # Run log and task dispatch concurrently
    await _log(candidate, "outbound", "system", msg)
    _get_reply_task().delay(candidate.id, msg)


async def _handle_ai_fallback(candidate, message: str) -> None:
    history = await ConversationLog.aget_recent(candidate, limit=5)

    ai_reply, detected = await get_ai_whatsapp_response(
        candidate_message=message,
        candidate_name=candidate.full_name,
        role_name=candidate.role_name,
        job_description=candidate.job.content,
        candidate_status=candidate.status,
        history=history,
    )

    if candidate.status not in ("interested", "not_interested"):
        if detected == "interested":
            await asyncio.gather(
                candidate.amark_response("interested", "whatsapp"),
                clear_context(candidate.id),
            )
        elif detected == "not_interested":
            await asyncio.gather(
                candidate.amark_response("not_interested", "whatsapp"),
                clear_context(candidate.id),
            )

    await _log(candidate, "outbound", "ai", ai_reply, detected)
    _get_reply_task().delay(candidate.id, ai_reply)


# ── View ───────────────────────────────────────────────────────────────

@method_decorator(csrf_exempt, name="dispatch")
class WhatsAppWebhookView(APIView):

    async def post(self, request: Request) -> Response:
        phone   = request.data.get("From", "").replace("whatsapp:", "").strip()
        message = request.data.get("Body", "").strip()

        if not phone or not message:
            return Response({"status": "bad request"}, status=400)

        candidate = await Candidate.aget_by_phone_or_none(phone)
        if candidate is None:
            logger.warning("[WEBHOOK] Unknown phone — %s", phone)
            return Response({"status": "candidate not found"}, status=404)

        await _log(candidate, "inbound", "candidate", message)

        intent = await resolve_intent(candidate.id, message)

        # ── Already decided flow ───────────────────────────────────────
        if candidate.status in ("interested", "not_interested"):

            if intent in JD_QUESTION_INTENTS or (intent and intent.startswith("jd_")):
                pass

            elif intent is None:
                ctx = await get_context(candidate.id)
                if ctx != "main":
                    await clear_context(candidate.id)
                    _get_reply_task().delay(
                        candidate.id,
                        main_menu_text(candidate.full_name, candidate.role_name),
                    )
                else:
                    await _handle_ai_fallback(candidate, message)
                return Response({"status": "received"})

            elif intent == "interested" and candidate.status == "interested":
                reply = (
                    f"Hi {candidate.full_name}! 😊\n\n"
                    f"You have already confirmed your interest in the "
                    f"*{candidate.role_name}* position.\n\n"
                    f"Our recruitment team will reach out to you very soon. "
                    f"Feel free to ask any questions about the role!"
                )
                await _log(candidate, "outbound", "system", reply, "interested")
                _get_reply_task().delay(candidate.id, reply)
                return Response({"status": "received"})

            elif intent == "interested" and candidate.status == "not_interested":
                reply = (
                    f"Wonderful! We are glad you changed your mind, {candidate.full_name}! 😊\n\n"
                    f"Our recruitment team will reach out to you very soon "
                    f"with the next steps.\n\nHave a great day!"
                )
                await asyncio.gather(
                    candidate.amark_response("interested", "whatsapp"),
                    clear_context(candidate.id),
                    _log(candidate, "outbound", "system", reply, "interested"),
                )
                _get_reply_task().delay(candidate.id, reply)
                return Response({"status": "received"})

            elif intent == "not_interested" and candidate.status == "interested":
                reply = (
                    f"Thank you for letting us know, {candidate.full_name}.\n\n"
                    f"We will keep your profile on file for future opportunities.\n\n"
                    f"All the best! 👍"
                )
                await asyncio.gather(
                    candidate.amark_response("not_interested", "whatsapp"),
                    clear_context(candidate.id),
                    _log(candidate, "outbound", "system", reply, "not_interested"),
                )
                _get_reply_task().delay(candidate.id, reply)
                return Response({"status": "received"})

            elif intent == "not_interested" and candidate.status == "not_interested":
                reply = (
                    f"Hi {candidate.full_name},\n\n"
                    f"You had previously indicated you are not interested.\n\n"
                    f"If you change your mind anytime, reply *YES* and we would "
                    f"love to have you on board! 😊"
                )
                await _log(candidate, "outbound", "system", reply, "not_interested")
                _get_reply_task().delay(candidate.id, reply)
                return Response({"status": "received"})

        # ── Main flow ──────────────────────────────────────────────────

        if intent is None:
            ctx = await get_context(candidate.id)
            if ctx != "main":
                await clear_context(candidate.id)
                _get_reply_task().delay(
                    candidate.id,
                    main_menu_text(candidate.full_name, candidate.role_name),
                )
            else:
                await _handle_ai_fallback(candidate, message)
            return Response({"status": "received"})

        if intent == "interested":
            reply = (
                f"Thank you for your interest, {candidate.full_name}! 😊\n\n"
                f"Our recruitment team will reach out to you very soon "
                f"with the next steps.\n\nHave a great day!"
            )
            await asyncio.gather(
                candidate.amark_response("interested", "whatsapp"),
                clear_context(candidate.id),
                _log(candidate, "outbound", "system", reply, "interested"),
            )
            _get_reply_task().delay(candidate.id, reply)

        elif intent == "not_interested":
            reply = (
                f"Thank you for letting us know, {candidate.full_name}.\n\n"
                f"We will keep your profile on file for future opportunities.\n\n"
                f"All the best! 👍"
            )
            await asyncio.gather(
                candidate.amark_response("not_interested", "whatsapp"),
                clear_context(candidate.id),
                _log(candidate, "outbound", "system", reply, "not_interested"),
            )
            _get_reply_task().delay(candidate.id, reply)

        elif intent == "back_main":
            await clear_context(candidate.id)
            _get_reply_task().delay(
                candidate.id,
                main_menu_text(candidate.full_name, candidate.role_name),
            )

        elif intent == "menu_salary":
            await asyncio.gather(
                set_context(candidate.id, "salary"),
            )
            _get_reply_task().delay(candidate.id, SALARY_MENU)

        elif intent == "menu_responsibilities":
            await set_context(candidate.id, "responsibilities")
            _get_reply_task().delay(candidate.id, RESPONSIBILITIES_MENU)

        elif intent == "menu_location":
            await set_context(candidate.id, "location")
            _get_reply_task().delay(candidate.id, LOCATION_MENU)

        elif intent == "menu_notice_period":
            await set_context(candidate.id, "notice_period")
            _get_reply_task().delay(candidate.id, NOTICE_MENU)

        elif intent == "menu_benefits":
            await set_context(candidate.id, "benefits")
            _get_reply_task().delay(candidate.id, BENEFITS_MENU)

        elif intent.startswith("jd_"):
            await _serve_jd_answer(candidate, intent[3:])

        elif intent in JD_FIELDS:
            await _serve_jd_answer(candidate, intent)

        return Response({"status": "received"})