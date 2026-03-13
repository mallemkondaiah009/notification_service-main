"""
Core call logic — separated from HTTP layer for testability.
"""
import re
import json
import logging

from shared.redis_client import redis_client, safe_incr
from shared.jd_parser import extract_answer, match_speech_to_field, FRIENDLY_LABELS
from .ai import get_ai_response

logger = logging.getLogger("call_service")

HISTORY_TTL = 60 * 60
MAX_HISTORY  = 6

# ── Direct speech → intent map ────────────────────────────────────────
SPEECH_INTENT_MAP = {
    # ── Interested ────────────────────────────────────────────────────
    "yes": "interested",
    "yeah": "interested",
    "yep": "interested",
    "yup": "interested",
    "sure": "interested",
    "okay": "interested",
    "ok": "interested",
    "ofcourse": "interested",
    "of course": "interested",
    "definitely": "interested",
    "absolutely": "interested",
    "certainly": "interested",
    "why not": "interested",
    "sounds good": "interested",
    "sounds great": "interested",
    "that sounds good": "interested",
    "that sounds great": "interested",
    "interested": "interested",
    "i am interested": "interested",
    "i'm interested": "interested",
    "yes interested": "interested",
    "yes i am interested": "interested",
    "yes i'm interested": "interested",
    "yes i am interested in this": "interested",
    "yes i am interested in this role": "interested",
    "yes i am interested in this position": "interested",
    "yes i'm interested in this role": "interested",
    "yes i'm interested in this position": "interested",
    "i am interested in this role": "interested",
    "i am interested in this position": "interested",
    "i'm interested in this role": "interested",
    "i'm interested in this position": "interested",
    "i am very interested": "interested",
    "i'm very interested": "interested",
    "very interested": "interested",
    "i would be interested": "interested",
    "i would like to apply": "interested",
    "i want to apply": "interested",
    "i want to join": "interested",
    "i will join": "interested",
    "i would like to join": "interested",
    "i want to proceed": "interested",
    "i would like to proceed": "interested",
    "please proceed": "interested",
    "yes please proceed": "interested",
    "yes go ahead": "interested",
    "go ahead": "interested",
    "i am in": "interested",
    "i'm in": "interested",
    "count me in": "interested",
    "i am open to this": "interested",
    "i am open to it": "interested",
    "i am open": "interested",
    "yes i want this job": "interested",
    "i want this job": "interested",
    "i need this job": "interested",
    "this sounds like a good opportunity": "interested",
    "this looks good": "interested",
    "this sounds good": "interested",
    "i like this role": "interested",
    "i like this position": "interested",
    "i like this opportunity": "interested",

    # ── Not Interested ────────────────────────────────────────────────
    "no": "not_interested",
    "nope": "not_interested",
    "nah": "not_interested",
    "no thanks": "not_interested",
    "no thank you": "not_interested",
    "not interested": "not_interested",
    "not really": "not_interested",
    "not right now": "not_interested",
    "not at this time": "not_interested",
    "not at the moment": "not_interested",
    "i am not interested": "not_interested",
    "i'm not interested": "not_interested",
    "no i am not interested": "not_interested",
    "no i'm not interested": "not_interested",
    "i am not interested in this": "not_interested",
    "i am not interested in this role": "not_interested",
    "i am not interested in this position": "not_interested",
    "i'm not interested in this role": "not_interested",
    "i'm not interested in this position": "not_interested",
    "no i am not interested in this role": "not_interested",
    "no i am not interested in this position": "not_interested",
    "i don't think so": "not_interested",
    "i dont think so": "not_interested",
    "i am not looking": "not_interested",
    "i'm not looking": "not_interested",
    "i am not looking for a job": "not_interested",
    "i am not looking for a change": "not_interested",
    "i'm not looking for a change": "not_interested",
    "not looking for a change": "not_interested",
    "not looking for change": "not_interested",
    "i am happy with my current job": "not_interested",
    "i am happy where i am": "not_interested",
    "i have a job": "not_interested",
    "i already have a job": "not_interested",
    "i am settled": "not_interested",
    "i am not willing": "not_interested",
    "i'm not willing": "not_interested",
    "not willing": "not_interested",
    "i will pass": "not_interested",
    "i'll pass": "not_interested",
    "please remove my number": "not_interested",
    "remove my number": "not_interested",
    "do not call again": "not_interested",
    "don't call again": "not_interested",
    "stop calling": "not_interested",
    "this is not for me": "not_interested",
    "this role is not for me": "not_interested",
    "this position is not for me": "not_interested",
    "not suitable for me": "not_interested",
    "not the right fit": "not_interested",
    "not a good fit": "not_interested",

    # ── Salary ────────────────────────────────────────────────────────
    "salary": "salary_basic",
    "pay": "salary_basic",
    "what is the salary": "salary_basic",
    "what is the pay": "salary_basic",
    "how much salary": "salary_basic",
    "how much is the salary": "salary_basic",
    "how much will i get": "salary_basic",
    "how much do you pay": "salary_basic",
    "what will i earn": "salary_basic",
    "tell me about the salary": "salary_basic",
    "salary details": "salary_basic",
    "monthly salary": "salary_basic",
    "fixed salary": "salary_basic",
    "basic salary": "salary_basic",
    "basic pay": "salary_basic",
    "ctc": "salary_ctc",
    "package": "salary_ctc",
    "total ctc": "salary_ctc",
    "annual ctc": "salary_ctc",
    "what is the ctc": "salary_ctc",
    "what is the package": "salary_ctc",
    "total package": "salary_ctc",
    "annual package": "salary_ctc",
    "yearly salary": "salary_ctc",
    "annual salary": "salary_ctc",
    "bonus": "salary_variables",
    "variable": "salary_variables",
    "incentive": "salary_variables",
    "is there a bonus": "salary_variables",
    "any bonus": "salary_variables",
    "what about bonus": "salary_variables",
    "variable pay": "salary_variables",
    "performance bonus": "salary_variables",
    "increment": "salary_increment",
    "hike": "salary_increment",
    "appraisal": "salary_increment",
    "salary hike": "salary_increment",
    "salary increment": "salary_increment",
    "pay raise": "salary_increment",
    "raise": "salary_increment",
    "when is appraisal": "salary_increment",

    # ── Responsibilities ──────────────────────────────────────────────
    "responsibilities": "resp_daily",
    "duties": "resp_daily",
    "role": "resp_daily",
    "what is the role": "resp_daily",
    "what will i do": "resp_daily",
    "what is my role": "resp_daily",
    "what is the job": "resp_daily",
    "job duties": "resp_daily",
    "daily tasks": "resp_daily",
    "what kind of work": "resp_daily",
    "what is the work": "resp_daily",
    "tell me about the role": "resp_daily",
    "tell me about the job": "resp_daily",
    "what does the job involve": "resp_daily",
    "what will be my responsibilities": "resp_daily",
    "key responsibilities": "resp_daily",
    "skills": "resp_skills",
    "requirements": "resp_skills",
    "what skills are required": "resp_skills",
    "what skills do you need": "resp_skills",
    "required skills": "resp_skills",
    "tech stack": "resp_skills",
    "what technologies": "resp_skills",
    "technical skills": "resp_skills",
    "what experience is required": "resp_skills",
    "years of experience": "resp_skills",
    "experience required": "resp_skills",
    "qualifications": "resp_skills",
    "team": "resp_team",
    "reporting": "resp_team",
    "who will i report to": "resp_team",
    "who is my manager": "resp_team",
    "team size": "resp_team",
    "how many people in the team": "resp_team",
    "team structure": "resp_team",
    "department": "resp_team",
    "growth": "resp_growth",
    "career": "resp_growth",
    "career growth": "resp_growth",
    "promotion": "resp_growth",
    "career path": "resp_growth",
    "growth opportunities": "resp_growth",
    "is there growth": "resp_growth",
    "can i grow": "resp_growth",
    "learning opportunities": "resp_growth",
    "training": "resp_growth",

    # ── Location ──────────────────────────────────────────────────────
    "location": "loc_city",
    "city": "loc_city",
    "office": "loc_city",
    "office location": "loc_city",
    "where is the office": "loc_city",
    "which city": "loc_city",
    "where is the job": "loc_city",
    "job location": "loc_city",
    "where do i have to work": "loc_city",
    "remote": "loc_remote",
    "hybrid": "loc_remote",
    "wfh": "loc_remote",
    "work from home": "loc_remote",
    "is it remote": "loc_remote",
    "can i work from home": "loc_remote",
    "is there wfh": "loc_remote",
    "is it hybrid": "loc_remote",
    "work mode": "loc_remote",
    "do i have to come to office": "loc_remote",
    "travel": "loc_travel",
    "do i have to travel": "loc_travel",
    "is there travel": "loc_travel",
    "travel requirement": "loc_travel",
    "field work": "loc_travel",

    # ── Notice Period ─────────────────────────────────────────────────
    "notice": "notice_duration",
    "notice period": "notice_duration",
    "what is the notice period": "notice_duration",
    "how long is the notice period": "notice_duration",
    "how many days notice": "notice_duration",
    "when can i join": "notice_duration",
    "joining time": "notice_duration",
    "buyout": "notice_buyout",
    "notice buyout": "notice_buyout",
    "can you buy out my notice": "notice_buyout",
    "will you pay for notice": "notice_buyout",
    "immediate": "notice_immediate",
    "immediate joining": "notice_immediate",
    "i can join immediately": "notice_immediate",
    "can join immediately": "notice_immediate",
    "available immediately": "notice_immediate",

    # ── Benefits ──────────────────────────────────────────────────────
    "insurance": "ben_insurance",
    "medical": "ben_insurance",
    "health insurance": "ben_insurance",
    "medical insurance": "ben_insurance",
    "is there insurance": "ben_insurance",
    "do you provide insurance": "ben_insurance",
    "mediclaim": "ben_insurance",
    "leave": "ben_leaves",
    "leaves": "ben_leaves",
    "paid leave": "ben_leaves",
    "how many leaves": "ben_leaves",
    "leave policy": "ben_leaves",
    "holidays": "ben_leaves",
    "how many holidays": "ben_leaves",
    "vacation": "ben_leaves",
    "time off": "ben_leaves",
    "food": "ben_food",
    "cab": "ben_food",
    "transport": "ben_food",
    "food allowance": "ben_food",
    "cab facility": "ben_food",
    "travel allowance": "ben_food",
    "conveyance": "ben_food",
    "pick and drop": "ben_food",
    "perks": "ben_other",
    "benefits": "ben_other",
    "other benefits": "ben_other",
    "what are the benefits": "ben_other",
    "any other benefits": "ben_other",
    "extra perks": "ben_other",
    "stock options": "ben_other",
    "esop": "ben_other",
    "laptop": "ben_other",
    "gym": "ben_other",
}

# ── All known JD field keys ───────────────────────────────────────────
JD_FIELDS = {
    "salary_basic", "salary_ctc", "salary_variables", "salary_increment",
    "resp_daily", "resp_skills", "resp_team", "resp_growth",
    "loc_city", "loc_remote", "loc_travel",
    "notice_duration", "notice_buyout", "notice_immediate",
    "ben_insurance", "ben_leaves", "ben_food", "ben_other",
}

# Pre-sort keys by length descending — done once at startup
_SORTED_INTENT_KEYS = sorted(SPEECH_INTENT_MAP.keys(), key=len, reverse=True)


def _match_intent_from_speech(normalized):
    """
    1. Exact match first
    2. Partial match — longest key wins
       e.g. "not interested" matches before "interested"
    """
    if normalized in SPEECH_INTENT_MAP:
        return SPEECH_INTENT_MAP[normalized]

    for key in _SORTED_INTENT_KEYS:
        if key in normalized:
            return SPEECH_INTENT_MAP[key]

    return None


def _clean_for_voice(text):
    """Strip markdown formatting for TTS."""
    text = re.sub(r"\*+", "", text)
    text = re.sub(r"_+", "", text)
    text = re.sub(r"#+\s*", "", text)
    text = re.sub(r"^\s*[-•]\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n+", ". ", text)
    text = re.sub(r"\.\s*\.", ".", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _get_jd_answer(button_id, job_description, role_name="this role"):
    """
    Reads directly from candidate's job_description.
    Falls back to dynamic default message using role_name if JD has no info.
    No Redis cache — always reads live from JD.
    """
    label, answer = extract_answer(button_id, job_description)

    if answer:
        answer = _clean_for_voice(answer)
        logger.info(f"[CALL] JD direct hit — field={button_id}")
        return label, answer

    # JD has no info — use dynamic default with role name
    logger.info(f"[CALL] JD miss — using default for field={button_id}")
    defaults = {
        "salary_basic":     f"The basic salary details for the {role_name} position will be discussed during the interview.",
        "salary_ctc":       f"The total CTC for the {role_name} position will be shared by our recruitment team.",
        "salary_variables": f"Variable pay and bonus details for the {role_name} position will be discussed during the interview.",
        "salary_increment": f"Increment and appraisal details for the {role_name} position will be shared by the HR team.",
        "resp_daily":       f"The daily responsibilities for the {role_name} position will be discussed during the interview.",
        "resp_skills":      f"The required skills for the {role_name} position will be discussed during the interview.",
        "resp_team":        f"Team structure and reporting details for the {role_name} position will be shared during the interview.",
        "resp_growth":      f"There are good growth opportunities in the {role_name} position. Details will be shared during the interview.",
        "loc_city":         f"The office location for the {role_name} position will be shared by our recruitment team.",
        "loc_remote":       f"The work mode for the {role_name} position will be discussed during the interview.",
        "loc_travel":       f"Travel requirements for the {role_name} position will be discussed during the interview.",
        "notice_duration":  f"Notice period details for the {role_name} position will be discussed during the interview.",
        "notice_buyout":    f"Notice buyout options for the {role_name} position will be discussed with our HR team.",
        "notice_immediate": f"Immediate joining options for the {role_name} position will be discussed during the interview.",
        "ben_insurance":    f"Health insurance and medical benefits for the {role_name} position will be shared during the interview.",
        "ben_leaves":       f"Leave policy details for the {role_name} position will be shared by the HR team.",
        "ben_food":         f"Food and transport benefit details for the {role_name} position will be discussed during the interview.",
        "ben_other":        f"Additional perks and benefits for the {role_name} position will be discussed during the interview.",
    }
    label = FRIENDLY_LABELS.get(button_id, button_id.replace("_", " ").title())
    default = defaults.get(button_id, f"Details for {label} for the {role_name} position will be discussed during the interview.")
    return label, default


def get_call_history(candidate_id):
    try:
        raw = redis_client.get(f"call_history:{candidate_id}")
        return json.loads(raw) if raw else []
    except Exception:
        return []


def append_call_history(candidate_id, role, content):
    try:
        history = get_call_history(candidate_id)
        history.append({"role": role, "content": content})
        history = history[-MAX_HISTORY:]
        redis_client.set(
            f"call_history:{candidate_id}",
            json.dumps(history),
            ex=HISTORY_TTL,
        )
    except Exception:
        pass


def clear_call_history(candidate_id):
    try:
        redis_client.delete(f"call_history:{candidate_id}")
    except Exception:
        pass


def handle_call_speech(candidate, speech):
    """
    Returns (spoken_reply, detected_status, source).
    source = 'jd' | 'ai' | 'duplicate'

    Flow:
    1. Exact + partial intent map         → instant, no DB/Redis
    2. Known JD field → read from JD      → JD answer or dynamic default
    3. Fuzzy sentence match → read from JD
    4. AI fallback                         → only truly unknown sentences
    """

    # ── Duplicate request lock ────────────────────────────────────────
    lock_key = f"call_lock:{candidate.id}:{hash(speech)}"
    if not redis_client.set(lock_key, "1", nx=True, ex=5):
        return None, "duplicate", "lock"

    normalized = speech.strip().lower()

    # ── Step 1: Intent map — exact then partial ───────────────────────
    direct_intent = _match_intent_from_speech(normalized)

    # ── Interested ────────────────────────────────────────────────────
    if direct_intent == "interested":
        clear_call_history(candidate.id)
        safe_incr("stats:call_jd_hits")
        logger.info(f"[CALL] Direct intent: interested — candidate={candidate.id}")
        return (
            f"Thank you for your interest, {candidate.full_name}! "
            f"You have shown interest in the {candidate.role_name} position. "
            f"Our recruitment team will reach out to you very soon with the next steps. "
            f"Have a great day!",
            "interested",
            "jd",
        )

    # ── Not Interested ────────────────────────────────────────────────
    if direct_intent == "not_interested":
        clear_call_history(candidate.id)
        safe_incr("stats:call_jd_hits")
        logger.info(f"[CALL] Direct intent: not_interested — candidate={candidate.id}")
        return (
            f"Thank you for letting us know, {candidate.full_name}. "
            f"We will keep your profile on file for future {candidate.role_name} opportunities. "
            f"All the best!",
            "not_interested",
            "jd",
        )

    # ── Known JD field ────────────────────────────────────────────────
    if direct_intent and direct_intent in JD_FIELDS:
        label, answer = _get_jd_answer(
            direct_intent,
            candidate.job_description,
            candidate.role_name,
        )
        spoken_reply = (
            f"Regarding {label} for the {candidate.role_name} position. "
            f"{answer}. "
            f"Do you have any other questions, or are you interested in this position?"
        )
        safe_incr("stats:call_jd_hits")
        logger.info(f"[CALL] Direct JD hit — candidate={candidate.id} field={label}")
        append_call_history(candidate.id, "user", speech)
        append_call_history(candidate.id, "assistant", spoken_reply)
        return spoken_reply, "unclear", "jd"

    # ── Step 2: Fuzzy match for full sentences ────────────────────────
    button_id = match_speech_to_field(speech)

    if button_id and button_id in JD_FIELDS:
        label, answer = _get_jd_answer(
            button_id,
            candidate.job_description,
            candidate.role_name,
        )
        if answer:
            spoken_reply = (
                f"Regarding {label} for the {candidate.role_name} position. "
                f"{answer}. "
                f"Do you have any other questions, or are you interested in this position?"
            )
            safe_incr("stats:call_jd_hits")
            logger.info(f"[CALL] Fuzzy JD hit — candidate={candidate.id} field={button_id}")
            append_call_history(candidate.id, "user", speech)
            append_call_history(candidate.id, "assistant", spoken_reply)
            return spoken_reply, "unclear", "jd"

    # ── Step 3: AI fallback — only truly unknown sentences ────────────
    safe_incr("stats:call_ai_hits")
    logger.info(f"[CALL] AI fallback — candidate={candidate.id} speech='{speech}'")

    history = get_call_history(candidate.id)

    ai_response, detected_status = get_ai_response(
        candidate_speech=speech,
        candidate_name=candidate.full_name,
        role_name=candidate.role_name,
        job_description=candidate.job_description,
        history=history,
    )

    append_call_history(candidate.id, "user", speech)
    append_call_history(candidate.id, "assistant", ai_response)

    if detected_status in ("interested", "not_interested"):
        clear_call_history(candidate.id)

    return ai_response, detected_status, "ai"