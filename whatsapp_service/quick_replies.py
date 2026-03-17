import redis.asyncio as aioredis
from django.conf import settings

CONTEXT_TTL = 60 * 60

# DB1 — conversation context only
_redis = aioredis.from_url(settings.REDIS_CONTEXT_URL, decode_responses=True)

async def set_context(candidate_id, context: str) -> None:
    await _redis.set(f"wa_ctx:{candidate_id}", context, ex=CONTEXT_TTL)

async def get_context(candidate_id) -> str:
    return await _redis.get(f"wa_ctx:{candidate_id}") or "main"

async def clear_context(candidate_id) -> None:
    await _redis.delete(f"wa_ctx:{candidate_id}")

# ── Intent + topic maps (pure Python — no async needed) ───────────────

INTENT_MAP = {
    "yes": "interested", "yeah": "interested", "yep": "interested",
    "yup": "interested", "sure": "interested", "okay": "interested",
    "ok": "interested", "of course": "interested", "ofcourse": "interested",
    "definitely": "interested", "absolutely": "interested",
    "certainly": "interested", "why not": "interested",
    "sounds good": "interested", "sounds great": "interested",
    "interested": "interested", "i am interested": "interested",
    "i'm interested": "interested", "yes interested": "interested",
    "i am very interested": "interested", "i'm very interested": "interested",
    "i would like to apply": "interested", "i want to apply": "interested",
    "i want to join": "interested", "i will join": "interested",
    "i am in": "interested", "i'm in": "interested",
    "count me in": "interested", "go ahead": "interested",
    "please proceed": "interested", "i want this job": "interested",
    "i need this job": "interested", "haan": "interested",
    "haan ji": "interested", "bilkul": "interested",
    "zaroor": "interested", "ha": "interested",

    "no": "not_interested", "nope": "not_interested", "nah": "not_interested",
    "no thanks": "not_interested", "no thank you": "not_interested",
    "not interested": "not_interested", "not really": "not_interested",
    "not right now": "not_interested", "not at this time": "not_interested",
    "i am not interested": "not_interested", "i'm not interested": "not_interested",
    "i don't think so": "not_interested", "i dont think so": "not_interested",
    "i am not looking": "not_interested", "i'm not looking": "not_interested",
    "i am not looking for a change": "not_interested",
    "not looking for a change": "not_interested",
    "i am happy with my current job": "not_interested",
    "i am happy where i am": "not_interested",
    "i will pass": "not_interested", "i'll pass": "not_interested",
    "please remove my number": "not_interested",
    "remove my number": "not_interested",
    "do not call again": "not_interested", "don't call again": "not_interested",
    "stop calling": "not_interested", "not suitable for me": "not_interested",
    "not the right fit": "not_interested", "not a good fit": "not_interested",
    "nahi": "not_interested", "nahi chahiye": "not_interested",
    "nahi interested": "not_interested", "nahi hai": "not_interested",

    "0": "back_main", "back": "back_main", "main menu": "back_main",
    "menu": "back_main", "back to main menu": "back_main",
    "back to main": "back_main", "back to menu": "back_main",
}

_SORTED_INTENT_KEYS = sorted(INTENT_MAP.keys(), key=len, reverse=True)

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

TOPIC_KEYWORDS = {
    "salary_ctc": [
        "total package", "annual package", "annual salary",
        "yearly salary", "annual ctc", "total ctc", "ctc", "package",
    ],
    "salary_variables": [
        "variable pay", "performance bonus", "incentive", "variable", "bonus",
    ],
    "salary_increment": [
        "salary hike", "salary increment", "pay raise",
        "increment", "appraisal", "hike", "raise",
    ],
    "salary_basic": [
        "monthly salary", "basic salary", "fixed salary",
        "kitna milega", "kitna pay",
        "salary", "pay", "compensation", "stipend", "monthly", "fixed", "basic",
    ],
    "resp_skills": [
        "tech stack", "required skills", "technical skills",
        "what skills", "experience required", "years of experience",
        "qualifications", "technologies", "tools", "skills", "requirements",
    ],
    "resp_team": [
        "who will i report", "how many people", "team size",
        "team structure", "reporting", "manager", "department", "team",
    ],
    "resp_growth": [
        "career growth", "growth opportunities", "career path",
        "learning opportunities", "career", "promotion", "training", "growth",
    ],
    "resp_daily": [
        "daily tasks", "key responsibilities", "what will i do",
        "what is the work", "what does the job", "job duties",
        "tell me about the role", "what kind of work",
        "responsibilities", "duties", "role", "work",
    ],
    "loc_remote": [
        "work from home", "wfh", "remote work", "hybrid work",
        "can i work from home", "work mode", "remote", "hybrid", "online",
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
        "notice buyout", "buy out my notice", "pay for notice", "buyout",
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
        "health insurance", "medical insurance", "mediclaim", "insurance", "medical",
    ],
    "ben_leaves": [
        "paid leave", "how many leaves", "leave policy",
        "how many holidays", "vacation", "time off", "leaves", "leave", "holiday",
    ],
    "ben_food": [
        "food allowance", "cab facility", "travel allowance",
        "pick and drop", "conveyance", "transport", "food", "cab",
    ],
    "ben_other": [
        "stock options", "other benefits", "extra perks",
        "esop", "gym", "laptop", "perks", "benefits",
    ],
}

_SORTED_TOPIC_PAIRS = sorted(
    [(field, kw) for field, keywords in TOPIC_KEYWORDS.items() for kw in keywords],
    key=lambda x: len(x[1]),
    reverse=True,
)

MAIN_MENU_MAP = {
    "1": "menu_responsibilities",
    "2": "menu_salary",
    "3": "menu_notice_period",
    "4": "menu_location",
    "5": "menu_benefits",
}

SALARY_SUB_MAP    = {"1": "salary_basic", "2": "salary_ctc", "3": "salary_variables", "4": "salary_increment"}
RESP_SUB_MAP      = {"1": "resp_daily",   "2": "resp_skills", "3": "resp_team",        "4": "resp_growth"}
LOCATION_SUB_MAP  = {"1": "loc_city",     "2": "loc_remote",  "3": "loc_travel"}
NOTICE_SUB_MAP    = {"1": "notice_duration", "2": "notice_buyout", "3": "notice_immediate"}
BENEFITS_SUB_MAP  = {"1": "ben_insurance", "2": "ben_leaves",  "3": "ben_food",        "4": "ben_other"}

JD_FIELDS = frozenset(
    list(SALARY_SUB_MAP.values()) +
    list(RESP_SUB_MAP.values()) +
    list(LOCATION_SUB_MAP.values()) +
    list(NOTICE_SUB_MAP.values()) +
    list(BENEFITS_SUB_MAP.values())
)

# ── Pure-Python matchers ───────────────────────────────────────────────

def _match_intent(normalized: str) -> str | None:
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

def _detect_topic(normalized: str) -> str | None:
    for field, keyword in _SORTED_TOPIC_PAIRS:
        if keyword in normalized:
            return field
    return None

# ── Main resolver — async because it reads Redis context ──────────────

async def resolve_intent(candidate_id, message: str) -> str | None:
    normalized = message.strip().lower()
    context    = await get_context(candidate_id)

    # Tier 1: fast-path yes / no / navigation
    intent = _match_intent(normalized)
    if intent:
        return intent

    # Numbered quick replies inside sub-menu context
    sub_maps = {
        "salary":         SALARY_SUB_MAP,
        "responsibilities": RESP_SUB_MAP,
        "location":       LOCATION_SUB_MAP,
        "notice_period":  NOTICE_SUB_MAP,
        "benefits":       BENEFITS_SUB_MAP,
    }
    if context in sub_maps and normalized in sub_maps[context]:
        return sub_maps[context][normalized]

    # Main menu numbers
    if normalized in MAIN_MENU_MAP:
        return MAIN_MENU_MAP[normalized]

    # Tier 2: JD topic keyword match
    topic = _detect_topic(normalized)
    if topic:
        return f"jd_{topic}"

    # Tier 3: fall through → AI in views.py
    return None