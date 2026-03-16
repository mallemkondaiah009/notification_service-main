"""
Core call logic — 3-tier intent system.
No caching — reads JD live on every request.

Tier 1 — Fast-path yes/no     (~10-15% of calls) — instant
Tier 2 — JD keyword match     (~70-80% of calls) — instant, reads live from JD
Tier 3 — AI fallback          (~10-15% of calls) — GPT-4o only when needed
"""
import re
import json
import logging

from shared.redis_client import redis_client, safe_incr
from shared.jd_parser import extract_answer, FRIENDLY_LABELS
from .ai import get_ai_response

logger = logging.getLogger("call_service")

HISTORY_TTL            = 60 * 60
MAX_HISTORY            = 6
MAX_TURNS_BEFORE_CLOSE = MAX_HISTORY - 2

MAX_INTENT_WORDS = 8

QUESTION_SIGNALS = {
    "what", "when", "where", "which", "who", "how", "why",
    "tell me", "can you", "could you", "is there", "do you",
    "will there", "are there", "explain", "describe", "but",
    "salary", "ctc", "package", "pay", "compensation",
    "location", "city", "office", "remote", "hybrid", "wfh",
    "notice", "joining", "travel", "field work",
    "benefits", "insurance", "medical", "leave", "holiday",
    "bonus", "variable", "increment", "hike", "appraisal",
    "role", "work", "responsibilities", "duties", "skills",
    "team", "manager", "reporting", "growth", "career",
    "training", "promotion",
}


# ══════════════════════════════════════════════════════════════════════
# TIER 1 — Fast-path yes/no intent map
# ══════════════════════════════════════════════════════════════════════
INTENT_MAP = {
    # Interested
    "yes":                           "interested",
    "yeah":                          "interested",
    "yep":                           "interested",
    "yup":                           "interested",
    "sure":                          "interested",
    "okay":                          "interested",
    "ok":                            "interested",
    "of course":                     "interested",
    "ofcourse":                      "interested",
    "definitely":                    "interested",
    "absolutely":                    "interested",
    "certainly":                     "interested",
    "why not":                       "interested",
    "sounds good":                   "interested",
    "sounds great":                  "interested",
    "interested":                    "interested",
    "i am interested":               "interested",
    "i'm interested":                "interested",
    "yes interested":                "interested",
    "i am very interested":          "interested",
    "i'm very interested":           "interested",
    "i would like to apply":         "interested",
    "i want to apply":               "interested",
    "i want to join":                "interested",
    "i will join":                   "interested",
    "i am in":                       "interested",
    "i'm in":                        "interested",
    "count me in":                   "interested",
    "go ahead":                      "interested",
    "please proceed":                "interested",
    "i want this job":               "interested",
    "i need this job":               "interested",
    "haan":                          "interested",
    "haan ji":                       "interested",
    "bilkul":                        "interested",
    "zaroor":                        "interested",
    "ha":                            "interested",

    # Not interested
    "no":                            "not_interested",
    "nope":                          "not_interested",
    "nah":                           "not_interested",
    "no thanks":                     "not_interested",
    "no thank you":                  "not_interested",
    "not interested":                "not_interested",
    "not really":                    "not_interested",
    "not right now":                 "not_interested",
    "not at this time":              "not_interested",
    "i am not interested":           "not_interested",
    "i'm not interested":            "not_interested",
    "i don't think so":              "not_interested",
    "i dont think so":               "not_interested",
    "i am not looking":              "not_interested",
    "i'm not looking":               "not_interested",
    "i am not looking for a change": "not_interested",
    "not looking for a change":      "not_interested",
    "i am happy with my current job":"not_interested",
    "i am happy where i am":         "not_interested",
    "i will pass":                   "not_interested",
    "i'll pass":                     "not_interested",
    "please remove my number":       "not_interested",
    "remove my number":              "not_interested",
    "do not call again":             "not_interested",
    "don't call again":              "not_interested",
    "stop calling":                  "not_interested",
    "not suitable for me":           "not_interested",
    "not the right fit":             "not_interested",
    "not a good fit":                "not_interested",
    "nahi":                          "not_interested",
    "nahi chahiye":                  "not_interested",
    "nahi interested":               "not_interested",
    "nahi hai":                      "not_interested",
}

_SORTED_INTENT_KEYS = sorted(INTENT_MAP.keys(), key=len, reverse=True)


# ══════════════════════════════════════════════════════════════════════
# TIER 2 — JD topic keyword map
# ══════════════════════════════════════════════════════════════════════
TOPIC_KEYWORDS = {
    "salary_ctc": [
        "total package", "annual package", "annual salary",
        "yearly salary", "annual ctc", "total ctc", "ctc", "package",
    ],
    "salary_variables": [
        "variable pay", "performance bonus", "incentive",
        "variable", "bonus",
    ],
    "salary_increment": [
        "salary hike", "salary increment", "pay raise",
        "increment", "appraisal", "hike", "raise",
    ],
    "salary_basic": [
        "monthly salary", "basic salary", "fixed salary",
        "kitna milega", "kitna pay",
        "salary", "pay", "compensation", "stipend",
        "monthly", "fixed", "basic",
    ],
    "resp_skills": [
        "tech stack", "required skills", "technical skills",
        "what skills", "experience required", "years of experience",
        "qualifications", "technologies", "tools", "skills",
        "requirements",
    ],
    "resp_team": [
        "who will i report", "how many people", "team size",
        "team structure", "reporting", "manager",
        "department", "team",
    ],
    "resp_growth": [
        "career growth", "growth opportunities", "career path",
        "learning opportunities", "career", "promotion",
        "training", "growth",
    ],
    "resp_daily": [
        "daily tasks", "key responsibilities", "what will i do",
        "what is the work", "what does the job", "job duties",
        "tell me about the role", "what kind of work",
        "responsibilities", "duties", "role", "work",
    ],
    "loc_remote": [
        "work from home", "wfh", "remote work", "hybrid work",
        "can i work from home", "work mode",
        "remote", "hybrid", "online",
    ],
    "loc_travel": [
        "travel requirement", "field work", "do i have to travel",
        "is there travel", "travel",
    ],
    "loc_city": [
        "office location", "job location", "where is the office",
        "which city", "where is the job", "where do i have to work",
        "location", "city", "office",
    ],
    "notice_buyout": [
        "notice buyout", "buy out my notice", "pay for notice",
        "buyout",
    ],
    "notice_immediate": [
        "immediate joining", "join immediately", "available immediately",
        "can join immediately", "immediate",
    ],
    "notice_duration": [
        "how long is the notice", "how many days notice",
        "what is the notice period", "when can i join",
        "joining time", "notice period", "notice",
    ],
    "ben_insurance": [
        "health insurance", "medical insurance", "mediclaim",
        "insurance", "medical",
    ],
    "ben_leaves": [
        "paid leave", "how many leaves", "leave policy",
        "how many holidays", "vacation", "time off",
        "leaves", "leave", "holiday",
    ],
    "ben_food": [
        "food allowance", "cab facility", "travel allowance",
        "pick and drop", "conveyance",
        "transport", "food", "cab",
    ],
    "ben_other": [
        "stock options", "other benefits", "extra perks",
        "esop", "gym", "laptop",
        "perks", "benefits",
    ],
}

_SORTED_TOPIC_PAIRS = sorted(
    [
        (field, kw)
        for field, keywords in TOPIC_KEYWORDS.items()
        for kw in keywords
    ],
    key=lambda x: len(x[1]),
    reverse=True,
)


# ── Tier 1 matcher ────────────────────────────────────────────────────

def _match_intent(normalized: str) -> str | None:
    """
    Guards:
      1. Word count > 8 → not a clean yes/no → None
      2. Contains question/topic signal → mixed intent → None
    """
    if len(normalized.split()) > MAX_INTENT_WORDS:
        return None
    if any(signal in normalized for signal in QUESTION_SIGNALS):
        return None
    if normalized in INTENT_MAP:
        return INTENT_MAP[normalized]
    for key in _SORTED_INTENT_KEYS:
        if key in normalized:
            return INTENT_MAP[key]
    return None


# ── Tier 2 matcher ────────────────────────────────────────────────────

def _detect_topic(normalized: str) -> str | None:
    for field, keyword in _SORTED_TOPIC_PAIRS:
        if keyword in normalized:
            return field
    return None


# ── JD answer reader — live, no cache ────────────────────────────────

def _get_jd_answer(field: str, job_description: str, role_name: str) -> tuple[str, str]:
    """
    Reads the answer live from the job description every time.
    No caching — simple and always fresh.
    """
    label, answer = extract_answer(field, job_description)

    if answer:
        return label, _clean_for_voice(answer)

    label = FRIENDLY_LABELS.get(field, field.replace("_", " ").title())
    defaults = {
        "salary_basic":      f"The basic salary for the {role_name} position will be discussed during the interview.",
        "salary_ctc":        f"The total CTC for the {role_name} position will be shared by our recruitment team.",
        "salary_variables":  f"Variable pay and bonus details will be discussed during the interview.",
        "salary_increment":  f"Increment and appraisal details will be shared by the HR team.",
        "resp_daily":        f"The daily responsibilities for the {role_name} position will be discussed during the interview.",
        "resp_skills":       f"The required skills for the {role_name} position will be discussed during the interview.",
        "resp_team":         f"Team structure and reporting details will be shared during the interview.",
        "resp_growth":       f"There are good growth opportunities. Details will be shared during the interview.",
        "loc_city":          f"The office location for the {role_name} position will be shared by our recruitment team.",
        "loc_remote":        f"The work mode for the {role_name} position will be discussed during the interview.",
        "loc_travel":        f"Travel requirements will be discussed during the interview.",
        "notice_duration":   f"Notice period details will be discussed during the interview.",
        "notice_buyout":     f"Notice buyout options will be discussed with our HR team.",
        "notice_immediate":  f"Immediate joining options will be discussed during the interview.",
        "ben_insurance":     f"Health insurance and medical benefits will be shared during the interview.",
        "ben_leaves":        f"Leave policy details will be shared by the HR team.",
        "ben_food":          f"Food and transport benefit details will be discussed during the interview.",
        "ben_other":         f"Additional perks and benefits will be discussed during the interview.",
    }
    answer = defaults.get(field, f"Details for {label} will be discussed during the interview.")
    return label, answer


def _build_jd_reply(label: str, answer: str, role_name: str) -> str:
    return (
        f"Regarding {label} for the {role_name} position. "
        f"{answer}. "
        f"Do you have any other questions, or are you interested in this position?"
    )


def _lakhs_to_words(amount_str: str) -> str:
    try:
        n = int(float(amount_str.replace(",", "")))
    except ValueError:
        return amount_str
    if n >= 100_000:
        lakhs = n / 100_000
        return f"{int(lakhs)} lakhs" if lakhs == int(lakhs) else f"{lakhs:.1f} lakhs"
    elif n >= 1_000:
        thousands = n / 1_000
        return f"{int(thousands)} thousand" if thousands == int(thousands) else f"{thousands:.1f} thousand"
    return str(n)


def _convert_salary_range(match) -> str:
    raw = match.group(0)
    lpa_match = re.match(r"([\d.]+)\s*(?:to|-)\s*([\d.]+)\s*lpa", raw, re.IGNORECASE)
    if lpa_match:
        return f"{lpa_match.group(1)} lakhs per annum to {lpa_match.group(2)} lakhs per annum"
    lpa_single = re.match(r"([\d.]+)\s*lpa", raw, re.IGNORECASE)
    if lpa_single:
        return f"{lpa_single.group(1)} lakhs per annum"
    range_match = re.match(r"[₹Rs.\s]*([\d,]+)\s*(?:to|-)\s*[₹Rs.\s]*([\d,]+)", raw, re.IGNORECASE)
    if range_match:
        return f"{_lakhs_to_words(range_match.group(1))} to {_lakhs_to_words(range_match.group(2))}"
    single_match = re.match(r"[₹Rs.\s]*([\d,]+)", raw, re.IGNORECASE)
    if single_match:
        return _lakhs_to_words(single_match.group(1).replace(",", ""))
    return raw


def _clean_for_voice(text: str) -> str:
    text = re.sub(r"[\d.]+\s*(?:to|-)\s*[\d.]+\s*lpa|[\d.]+\s*lpa", _convert_salary_range, text, flags=re.IGNORECASE)
    text = re.sub(r"[₹]?\s*[\d,]+\s*(?:to|-)\s*[₹]?\s*[\d,]+|(?:Rs\.?\s*)[\d,]+\s*(?:to|-)?\s*(?:Rs\.?\s*)?[\d,]*", _convert_salary_range, text, flags=re.IGNORECASE)
    text = re.sub(r"[₹]\s*[\d,]+|Rs\.?\s*[\d,]+", _convert_salary_range, text, flags=re.IGNORECASE)
    text = re.sub(r"\b(\d{1,2})\s*-\s*(\d{1,2})\b", lambda m: f"{m.group(1)} to {m.group(2)}", text)
    day_map = {"mon": "Monday", "tue": "Tuesday", "wed": "Wednesday", "thu": "Thursday", "fri": "Friday", "sat": "Saturday", "sun": "Sunday"}
    text = re.sub(r"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s*-\s*(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b", lambda m: f"{day_map[m.group(1).lower()]} to {day_map[m.group(2).lower()]}", text, flags=re.IGNORECASE)
    text = re.sub(r"(\d+)\s*%", r"\1 percent", text)
    abbr_map = {r"\bp\.?a\.?\b": "per annum", r"\bp\.?m\.?\b": "per month", r"\bctc\b": "cost to company", r"\bwfh\b": "work from home", r"\byrs?\b": "years", r"\blpa\b": "lakhs per annum", r"\b&\b": "and"}
    for pattern, replacement in abbr_map.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    text = re.sub(r"\s*/\s*", " or ", text)
    text = re.sub(r"\*+", "", text)
    text = re.sub(r"_+", "", text)
    text = re.sub(r"#+\s*", "", text)
    text = re.sub(r"^\s*[-•]\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n+", ". ", text)
    text = re.sub(r"\s+-\s+", ", ", text)
    text = re.sub(r"\.\s*\.", ".", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ── Redis call history helpers (kept — needed for multi-turn) ─────────

def get_call_history(candidate_id: int) -> list:
    try:
        raw = redis_client.get(f"call_history:{candidate_id}")
        return json.loads(raw) if raw else []
    except Exception:
        return []


def append_call_history(candidate_id: int, role: str, content: str):
    try:
        history = get_call_history(candidate_id)
        history.append({"role": role, "content": content})
        history = history[-MAX_HISTORY:]
        redis_client.set(f"call_history:{candidate_id}", json.dumps(history), ex=HISTORY_TTL)
    except Exception:
        pass


def clear_call_history(candidate_id: int):
    try:
        redis_client.delete(f"call_history:{candidate_id}")
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════════════

def handle_call_speech(candidate, speech: str):
    """
    Returns (spoken_reply, detected_status, source).

    ┌──────────────────────────────────────────────────────────────┐
    │  Tier 1  Fast-path yes/no       ~10-15% of calls  <5ms      │
    │  Tier 2  JD keyword match       ~70-80% of calls  <5ms      │
    │  Tier 3  AI fallback            ~10-15% of calls  1-3s      │
    └──────────────────────────────────────────────────────────────┘
    """

    # ── Duplicate request lock (Redis — kept for call integrity) ─────
    lock_key = f"call_lock:{candidate.id}:{hash(speech)}"
    if not redis_client.set(lock_key, "1", nx=True, ex=5):
        return None, "duplicate", "lock"

    normalized = speech.strip().lower()

    # ── Tier 1: Fast-path yes/no ──────────────────────────────────────
    intent = _match_intent(normalized)

    if intent == "interested":
        clear_call_history(candidate.id)
        safe_incr("stats:call_jd_hits")
        logger.info(f"[CALL][T1] interested — candidate={candidate.id}")
        return (
            f"Thank you for your interest, {candidate.full_name}! "
            f"You have shown interest in the {candidate.role_name} position. "
            f"Our recruitment team will reach out to you very soon with the next steps. "
            f"Have a great day!",
            "interested",
            "jd",
        )

    if intent == "not_interested":
        clear_call_history(candidate.id)
        safe_incr("stats:call_jd_hits")
        logger.info(f"[CALL][T1] not_interested — candidate={candidate.id}")
        return (
            f"Thank you for letting us know, {candidate.full_name}. "
            f"We will keep your profile on file for future {candidate.role_name} opportunities. "
            f"All the best!",
            "not_interested",
            "jd",
        )

    # ── Tier 2: JD keyword match ──────────────────────────────────────
    topic = _detect_topic(normalized)

    if topic:
        label, answer = _get_jd_answer(topic, candidate.job_description, candidate.role_name)
        spoken_reply = _build_jd_reply(label, answer, candidate.role_name)
        safe_incr("stats:call_jd_hits")
        logger.info(f"[CALL][T2] JD match — candidate={candidate.id} field={topic}")
        append_call_history(candidate.id, "user", speech)
        append_call_history(candidate.id, "assistant", spoken_reply)
        return spoken_reply, "unclear", "jd"

    # ── Tier 3: AI fallback ───────────────────────────────────────────
    safe_incr("stats:call_ai_hits")
    logger.info(f"[CALL][T3] AI — candidate={candidate.id} speech='{speech}'")

    history = get_call_history(candidate.id)
    turn_count = len(history) // 2
    closing_hint = (
        "The conversation has been going on for a while. "
        "Gently wrap up — ask the candidate if they are ready to confirm "
        "their interest or if they have one final question."
        if turn_count >= MAX_TURNS_BEFORE_CLOSE else ""
    )

    ai_reply, detected_status = get_ai_response(
        candidate_speech=speech,
        candidate_name=candidate.full_name,
        role_name=candidate.role_name,
        job_description=candidate.job_description,
        history=history,
        closing_hint=closing_hint,
    )

    ai_reply = _clean_for_voice(ai_reply)
    append_call_history(candidate.id, "user", speech)
    append_call_history(candidate.id, "assistant", ai_reply)

    if detected_status in ("interested", "not_interested"):
        clear_call_history(candidate.id)

    return ai_reply, detected_status, "ai"