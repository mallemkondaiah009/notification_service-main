from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from candidate.models import Candidate, ConversationLog
from delivery_logs.models import DeliveryLog
from workers.tasks import send_whatsapp_reply_message
from .ai import get_ai_whatsapp_response
from .menus import (
    send_main_menu,
    send_salary_menu,
    send_responsibilities_menu,
    send_location_menu,
    send_notice_period_menu,
    send_benefits_menu,
    send_interest_buttons,
)
from shared.jd_parser import extract_answer, FRIENDLY_LABELS
from .quick_replies import resolve_intent, get_context, set_context, clear_context


def _log_delivery(candidate, message, status):
    DeliveryLog.objects.create(
        candidate=candidate,
        channel="whatsapp",
        recipient=candidate.phone,
        message=message,
        status=status,
    )


def _save_response(candidate, status):
    candidate.status = status
    candidate.responded_via = "whatsapp"
    candidate.responded_at = timezone.now()
    candidate.save()


def _log_conversation(candidate, direction, sender, message, ai_detected_status=None):
    ConversationLog.objects.create(
        candidate=candidate,
        channel="whatsapp",
        direction=direction,
        sender=sender,
        message=message,
        ai_detected_status=ai_detected_status,
    )


def _serve_jd_answer(candidate, field: str):
    """Tier 2 — extract answer from JD and send with interest buttons."""
    label, answer = extract_answer(field, candidate.job_description)
    if answer:
        context_msg = f"*{label}*\n\n{answer}"
    else:
        label = FRIENDLY_LABELS.get(field, field.replace("_", " ").title())
        context_msg = (
            f"We don't have specific details about *{label}* right now.\n\n"
            f"Feel free to type your question and our team will get back to you!"
        )
    _log_delivery(candidate, f"JD answer served: {label}", "success")
    _log_conversation(candidate, "outbound", "system", context_msg)
    send_interest_buttons(candidate, context_msg)


@api_view(["POST"])
def whatsapp_webhook(request):
    phone = request.data.get("From", "").replace("whatsapp:", "")
    message = request.data.get("Body", "").strip()

    try:
        candidate = Candidate.objects.get(phone=phone)
    except Candidate.DoesNotExist:
        return Response({"status": "candidate not found"})

    if not message:
        return Response({"status": "empty message"})

    _log_conversation(candidate, "inbound", "candidate", message)

    intent = resolve_intent(candidate.id, message)

    # ── Unrecognized input inside a sub-menu → back to main menu ─────
    if intent is None:
        current_context = get_context(candidate.id)
        if current_context != "main":
            clear_context(candidate.id)
            _log_conversation(candidate, "outbound", "system", "[Unrecognized in sub-menu → Main Menu]")
            send_main_menu(candidate)
            return Response({"status": "received"})

    # ── TIER 1: INTERESTED ────────────────────────────────────────────
    if intent == "interested":
        _save_response(candidate, "interested")
        clear_context(candidate.id)
        _log_delivery(candidate, "Candidate replied YES → Interested", "success")
        reply = (
            f"Thank you for your interest, {candidate.full_name}! 😊\n\n"
            f"Our recruitment team will reach out to you very soon "
            f"with the next steps.\n\nHave a great day!"
        )
        _log_conversation(candidate, "outbound", "system", reply, "interested")
        send_whatsapp_reply_message.delay(candidate.id, reply)

    # ── TIER 1: NOT INTERESTED ────────────────────────────────────────
    elif intent == "not_interested":
        _save_response(candidate, "not_interested")
        clear_context(candidate.id)
        _log_delivery(candidate, "Candidate replied NO → Not Interested", "success")
        reply = (
            f"Thank you for letting us know, {candidate.full_name}.\n\n"
            f"We will keep your profile on file for future opportunities.\n\n"
            f"All the best! 👍"
        )
        _log_conversation(candidate, "outbound", "system", reply, "not_interested")
        send_whatsapp_reply_message.delay(candidate.id, reply)

    # ── TIER 1: BACK TO MAIN MENU ─────────────────────────────────────
    elif intent == "back_main":
        clear_context(candidate.id)
        _log_conversation(candidate, "outbound", "system", "[Main Menu Sent]")
        send_main_menu(candidate)

    # ── MENU NAVIGATION ───────────────────────────────────────────────
    elif intent == "menu_salary":
        set_context(candidate.id, "salary")
        _log_conversation(candidate, "outbound", "system", "[Salary Sub-Menu Sent]")
        send_salary_menu(candidate)

    elif intent == "menu_responsibilities":
        set_context(candidate.id, "responsibilities")
        _log_conversation(candidate, "outbound", "system", "[Responsibilities Sub-Menu Sent]")
        send_responsibilities_menu(candidate)

    elif intent == "menu_location":
        set_context(candidate.id, "location")
        _log_conversation(candidate, "outbound", "system", "[Location Sub-Menu Sent]")
        send_location_menu(candidate)

    elif intent == "menu_notice_period":
        set_context(candidate.id, "notice_period")
        _log_conversation(candidate, "outbound", "system", "[Notice Period Sub-Menu Sent]")
        send_notice_period_menu(candidate)

    elif intent == "menu_benefits":
        set_context(candidate.id, "benefits")
        _log_conversation(candidate, "outbound", "system", "[Benefits Sub-Menu Sent]")
        send_benefits_menu(candidate)

    # ── TIER 2: DIRECT JD ANSWER (natural language topic match) ──────
    elif intent and intent.startswith("jd_"):
        field = intent[3:]  # strip "jd_" prefix → e.g. "salary_basic"
        _serve_jd_answer(candidate, field)

    # ── NUMBERED SUB-MENU ITEMS → extract from JD ────────────────────
    elif intent in (
        "salary_basic", "salary_ctc", "salary_variables", "salary_increment",
        "resp_daily", "resp_skills", "resp_team", "resp_growth",
        "loc_city", "loc_remote", "loc_travel",
        "notice_duration", "notice_buyout", "notice_immediate",
        "ben_insurance", "ben_leaves", "ben_food", "ben_other",
    ):
        _serve_jd_answer(candidate, intent)

    # ── TIER 3: AI FALLBACK ───────────────────────────────────────────
    else:
        ai_response, detected_status = get_ai_whatsapp_response(
            candidate_message=message,
            candidate_name=candidate.full_name,
            role_name=candidate.role_name,
            job_description=candidate.job_description,
        )

        if detected_status == "interested":
            _save_response(candidate, "interested")
            clear_context(candidate.id)
            _log_delivery(candidate, "AI detected: Interested", "success")
        elif detected_status == "not_interested":
            _save_response(candidate, "not_interested")
            clear_context(candidate.id)
            _log_delivery(candidate, "AI detected: Not Interested", "success")
        else:
            _log_delivery(candidate, "AI detected: Unclear", "failed")

        _log_conversation(candidate, "outbound", "ai", ai_response, detected_status)
        send_whatsapp_reply_message.delay(candidate.id, ai_response)

    return Response({"status": "received"})