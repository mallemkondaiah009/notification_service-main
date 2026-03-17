import logging

from adrf.views import APIView
from rest_framework.request import Request
from rest_framework.response import Response

from candidate.models import Candidate, ConversationLog
from shared.jd_parser import extract_answer, FRIENDLY_LABELS

from .ai import get_ai_whatsapp_response
from .quick_replies import (
    resolve_intent, get_context, set_context, clear_context, JD_FIELDS,
)
from workers.tasks import send_whatsapp_reply_task

logger = logging.getLogger("whatsapp.views")


# ── Helpers ────────────────────────────────────────────────────────────

async def _log(candidate, direction, sender, message, status=None) -> None:
    # If candidate already interested/not_interested,
    # never log a lower-priority status for outbound messages
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


async def _serve_jd_answer(candidate, field: str) -> None:
    from shared.jd_parser import extract_answer, FRIENDLY_LABELS
    label, answer = extract_answer(field, candidate.job_description)

    if answer:
        msg = f"*{label}*\n\n{answer}"
    else:
        label = FRIENDLY_LABELS.get(field, field.replace("_", " ").title())
        msg = (
            f"We don't have specific details about *{label}* right now.\n\n"
            f"Feel free to type your question and our team will get back to you!"
        )

    await _log(candidate, "outbound", "system", msg)
    # Fire through Celery — not direct
    send_whatsapp_reply_task.delay(candidate.id, msg)


# ── View ───────────────────────────────────────────────────────────────

class WhatsAppWebhook(APIView):

    async def post(self, request: Request) -> Response:
        phone   = request.data.get("From", "").replace("whatsapp:", "").strip()
        message = request.data.get("Body", "").strip()

        if not phone or not message:
            return Response({"status": "bad request"}, status=400)

        # ── Fetch candidate ────────────────────────────────────────────
        try:
            candidate = await Candidate.aget_by_phone(phone)
        except Candidate.DoesNotExist:
            logger.warning("[WEBHOOK] Unknown phone — %s", phone)
            return Response({"status": "candidate not found"}, status=404)

        # ── Log inbound ────────────────────────────────────────────────
        await _log(candidate, "inbound", "candidate", message)

        # ── Resolve intent ─────────────────────────────────────────────
        intent = await resolve_intent(candidate.id, message)

        # ── Unrecognised message ───────────────────────────────────────
        if intent is None:
            ctx = await get_context(candidate.id)
            if ctx != "main":
                await clear_context(candidate.id)
                # Back to main menu via Celery
                send_whatsapp_reply_task.delay(
                    candidate.id,
                    _main_menu_text(candidate.full_name, candidate.role_name),
                )
            else:
                # AI fallback
                ai_reply, detected = await get_ai_whatsapp_response(
                    candidate_message=message,
                    candidate_name=candidate.full_name,
                    role_name=candidate.role_name,
                    job_description=candidate.job_description,
                    candidate_status=candidate.status,
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

        # ── TIER 1: Interested ─────────────────────────────────────────
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

        # ── TIER 1: Not interested ─────────────────────────────────────
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

        # ── TIER 1: Back to main ───────────────────────────────────────
        elif intent == "back_main":
            await clear_context(candidate.id)
            send_whatsapp_reply_task.delay(
                candidate.id,
                _main_menu_text(candidate.full_name, candidate.role_name),
            )

        # ── Menu navigation ────────────────────────────────────────────
        elif intent == "menu_salary":
            await set_context(candidate.id, "salary")
            send_whatsapp_reply_task.delay(candidate.id, _SALARY_MENU)

        elif intent == "menu_responsibilities":
            await set_context(candidate.id, "responsibilities")
            send_whatsapp_reply_task.delay(candidate.id, _RESPONSIBILITIES_MENU)

        elif intent == "menu_location":
            await set_context(candidate.id, "location")
            send_whatsapp_reply_task.delay(candidate.id, _LOCATION_MENU)

        elif intent == "menu_notice_period":
            await set_context(candidate.id, "notice_period")
            send_whatsapp_reply_task.delay(candidate.id, _NOTICE_MENU)

        elif intent == "menu_benefits":
            await set_context(candidate.id, "benefits")
            send_whatsapp_reply_task.delay(candidate.id, _BENEFITS_MENU)

        # ── TIER 2: Natural language JD topic ─────────────────────────
        elif intent.startswith("jd_"):
            await _serve_jd_answer(candidate, intent[3:])

        # ── Numbered sub-menu JD fields ────────────────────────────────
        elif intent in JD_FIELDS:
            await _serve_jd_answer(candidate, intent)

        return Response({"status": "received"})


# ── Menu text helpers (pure strings — no Twilio call here) ─────────────

def _main_menu_text(name: str, role: str) -> str:
    return f"""👋 Hello {name}!

We are hiring for *{role}*.

Please reply with a number to know more:

*Job Details:*
1️⃣  Responsibilities
2️⃣  Salary & CTC
3️⃣  Notice Period
4️⃣  Work Location
5️⃣  Benefits & Perks

*Your Decision:*
✅  Reply *YES* — I'm Interested
❌  Reply *NO* — Not Interested

💬 Or type any question and we'll answer it!"""


_SALARY_MENU = """💰 *Salary Details*

Reply with a number:

1️⃣  Basic Salary
2️⃣  Total CTC
3️⃣  Variable / Bonus
4️⃣  Increment Policy

0️⃣  Back to Main Menu"""

_RESPONSIBILITIES_MENU = """📋 *Responsibilities*

Reply with a number:

1️⃣  Daily Tasks
2️⃣  Required Skills
3️⃣  Team & Reporting
4️⃣  Growth Opportunities

0️⃣  Back to Main Menu"""

_LOCATION_MENU = """📍 *Work Location*

Reply with a number:

1️⃣  Office City
2️⃣  Remote / Hybrid Policy
3️⃣  Travel Requirements

0️⃣  Back to Main Menu"""

_NOTICE_MENU = """📅 *Notice Period*

Reply with a number:

1️⃣  Notice Duration
2️⃣  Notice Buyout
3️⃣  Immediate Joiners

0️⃣  Back to Main Menu"""

_BENEFITS_MENU = """🎁 *Benefits & Perks*

Reply with a number:

1️⃣  Health Insurance
2️⃣  Leave Policy
3️⃣  Food & Transport
4️⃣  Other Perks

0️⃣  Back to Main Menu"""