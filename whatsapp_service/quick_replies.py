import redis.asyncio as aioredis
from django.conf import settings

CONTEXT_TTL = 60 * 60  # 1 hour

_redis = aioredis.from_url(settings.REDIS_CONTEXT_URL, decode_responses=True)


# ── Context helpers ────────────────────────────────────────────────────

async def set_context(candidate_id: int, context: str) -> None:
    try:
        await _redis.set(f"wa_ctx:{candidate_id}", context, ex=CONTEXT_TTL)
    except Exception:
        pass

async def get_context(candidate_id: int) -> str:
    try:
        return await _redis.get(f"wa_ctx:{candidate_id}") or "main"
    except Exception:
        return "main"

async def clear_context(candidate_id: int) -> None:
    try:
        await _redis.delete(f"wa_ctx:{candidate_id}")
    except Exception:
        pass


# ── Intent map — only unambiguous explicit confirmations ───────────────

INTENT_MAP = {
    # Interested
    "yes":                            "interested",
    "yeah":                           "interested",
    "yep":                            "interested",
    "yup":                            "interested",
    "yes please":                     "interested",
    "interested":                     "interested",
    "i am interested":                "interested",
    "i'm interested":                 "interested",
    "yes interested":                 "interested",
    "i am very interested":           "interested",
    "i'm very interested":            "interested",
    "i would like to apply":          "interested",
    "i want to apply":                "interested",
    "i want to join":                 "interested",
    "i will join":                    "interested",
    "i want to proceed":              "interested",
    "i am in":                        "interested",
    "i'm in":                         "interested",
    "count me in":                    "interested",
    "i want this job":                "interested",
    "i need this job":                "interested",
    "please share next steps":        "interested",
    "i would like to proceed":        "interested",
    "i am ready to proceed":          "interested",
    "sign me up":                     "interested",
    "haan":                           "interested",
    "haan ji":                        "interested",
    "haan interested":                "interested",
    "bilkul":                         "interested",
    "zaroor":                         "interested",
    "haan karunga":                   "interested",
    "haan karungi":                   "interested",

    # Not interested
    "no":                             "not_interested",
    "nope":                           "not_interested",
    "nah":                            "not_interested",
    "no thanks":                      "not_interested",
    "no thank you":                   "not_interested",
    "not interested":                 "not_interested",
    "not really":                     "not_interested",
    "not right now":                  "not_interested",
    "not at this time":               "not_interested",
    "i am not interested":            "not_interested",
    "i'm not interested":             "not_interested",
    "i don't think so":               "not_interested",
    "i dont think so":                "not_interested",
    "i am not looking":               "not_interested",
    "i'm not looking":                "not_interested",
    "i am not looking for a change":  "not_interested",
    "not looking for a change":       "not_interested",
    "i am happy with my current job": "not_interested",
    "i am happy where i am":          "not_interested",
    "i will pass":                    "not_interested",
    "i'll pass":                      "not_interested",
    "please remove my number":        "not_interested",
    "remove my number":               "not_interested",
    "do not call again":              "not_interested",
    "don't call again":               "not_interested",
    "stop calling":                   "not_interested",
    "not suitable for me":            "not_interested",
    "not the right fit":              "not_interested",
    "not a good fit":                 "not_interested",
    "this is not for me":             "not_interested",
    "not looking for change":         "not_interested",
    "nahi":                           "not_interested",
    "nahi chahiye":                   "not_interested",
    "nahi interested":                "not_interested",
    "nahi hai":                       "not_interested",
    "nahi karunga":                   "not_interested",
    "nahi karungi":                   "not_interested",
    "mujhe nahi karna":               "not_interested",

    # Navigation
    "0":                              "back_main",
    "back":                           "back_main",
    "main menu":                      "back_main",
    "menu":                           "back_main",
    "back to main menu":              "back_main",
    "back to main":                   "back_main",
    "back to menu":                   "back_main",
    "go back":                        "back_main",
    "start over":                     "back_main",
    "restart":                        "back_main",
    "home":                           "back_main",
}

_SORTED_INTENT_KEYS = sorted(INTENT_MAP.keys(), key=len, reverse=True)

MAX_INTENT_WORDS = 8

# If ANY of these appear in the message → skip intent map → go to topic/AI
QUESTION_SIGNALS = {
    "what", "when", "where", "which", "who", "how", "why", "whose",
    "tell me", "can you", "could you", "is there", "do you", "did you",
    "will there", "are there", "explain", "describe", "give me",
    "let me know", "i want to know", "i need to know", "please tell",
    "can i know", "want to know", "would like to know",
    "but", "however", "also", "and what", "what about", "how about",
    "one more", "another question",
    "salary", "ctc", "package", "pay", "compensation", "stipend",
    "basic", "variable", "bonus", "incentive", "increment", "hike",
    "appraisal", "raise",
    "location", "city", "office", "remote", "hybrid", "wfh", "onsite",
    "work from home", "work from anywhere", "flexible",
    "notice", "joining", "buyout", "immediate",
    "travel", "field work", "client visit", "relocation",
    "benefits", "insurance", "medical", "leave", "holiday", "vacation",
    "food", "cab", "transport", "allowance", "perks", "laptop", "gym",
    "esop", "stock",
    "role", "work", "responsibilities", "duties", "skills", "tech",
    "team", "manager", "reporting", "growth", "career", "promotion",
    "training", "learning", "development",
    "experience", "qualification", "requirement",
    "ok", "okay", "sure", "alright", "fine", "got it", "i see",
    "sounds", "great", "good", "nice", "interesting", "cool",
    "tell more", "more details", "more info", "know more",
}

TOPIC_KEYWORDS = {
    "salary_ctc": [
        "total package", "annual package", "annual salary", "yearly salary",
        "annual ctc", "total ctc", "what is ctc", "what is the ctc",
        "how much is ctc", "total compensation", "ctc", "package",
    ],
    "salary_variables": [
        "variable pay", "performance bonus", "incentive pay",
        "is there bonus", "any bonus", "do you give bonus",
        "what about bonus", "sales incentive", "quarterly bonus",
        "annual bonus", "variable", "bonus", "incentive", "commission",
    ],
    "salary_increment": [
        "salary hike", "salary increment", "annual raise", "pay raise",
        "when is appraisal", "how often hike", "yearly increment",
        "salary review", "performance review",
        "increment", "appraisal", "hike", "raise",
    ],
    "salary_basic": [
        "monthly salary", "basic salary", "fixed salary", "base salary",
        "what is the salary", "how much salary", "how much will i get",
        "what will i get", "what is the pay", "how much do you pay",
        "monthly income", "fixed pay", "kitna milega", "kitna pay",
        "salary details", "salary", "pay", "compensation", "stipend",
        "monthly", "fixed", "basic",
    ],
    "resp_skills": [
        "tech stack", "required skills", "technical skills",
        "what skills", "what do you need", "what are the requirements",
        "what should i know", "what technologies", "what tools",
        "experience required", "years of experience",
        "qualifications", "skill set",
        "skills", "requirements", "technologies", "tools",
    ],
    "resp_team": [
        "who will i report to", "who do i report to", "who is my manager",
        "how many people", "team size", "team structure",
        "reporting structure", "who is the boss",
        "reporting", "manager", "department", "team",
    ],
    "resp_growth": [
        "career growth", "growth opportunities", "career path",
        "learning opportunities", "promotion policy", "future scope",
        "is there growth", "can i grow", "career development",
        "career", "promotion", "training", "upskill", "growth",
        "learning", "development",
    ],
    "resp_daily": [
        "day-to-day", "daily tasks", "key responsibilities",
        "what will i do", "what is my role", "what is the job",
        "what does the job involve", "what is the work",
        "what kind of work", "daily work", "role and responsibilities",
        "what will be my work", "what do i have to do",
        "job duties", "tell me about the role", "about the role",
        "responsibilities", "duties", "role", "work",
    ],
    "loc_remote": [
        "work from home", "wfh", "remote work", "hybrid work",
        "can i work from home", "is it remote", "is there wfh",
        "work from anywhere", "do i have to come to office",
        "is it hybrid", "work mode", "office or home", "flexible work",
        "remote", "hybrid", "onsite", "online",
    ],
    "loc_travel": [
        "travel requirement", "do i have to travel", "is there travel",
        "client travel", "field work", "site visits", "travel involved",
        "on-site visits", "client visits", "relocation", "travel",
    ],
    "loc_city": [
        "office location", "job location", "where is the office",
        "which city", "where is the job", "where do i have to work",
        "office address", "where is it located", "office city",
        "which location", "based in", "work from",
        "location", "city", "office",
    ],
    "notice_buyout": [
        "notice buyout", "buy out my notice", "will you pay for notice",
        "can you buy out my notice", "notice period buyout",
        "can i get buyout", "buyout",
    ],
    "notice_immediate": [
        "immediate joiner", "immediate joining", "joining immediately",
        "i can join immediately", "available immediately",
        "immediate availability", "can join right away",
        "no notice period", "can join", "immediate",
    ],
    "notice_duration": [
        "how long is the notice", "how many days notice",
        "what is the notice period", "when can i join",
        "how soon can i join", "notice period duration",
        "serving notice", "joining time",
        "notice period", "notice",
    ],
    "ben_insurance": [
        "health insurance", "medical insurance", "medical benefits",
        "health cover", "is there insurance", "do you provide insurance",
        "family insurance", "health benefits",
        "insurance", "medical", "mediclaim", "hospitalization",
    ],
    "ben_leaves": [
        "how many leaves", "leave policy", "how many holidays",
        "paid leave", "casual leave", "sick leave", "annual leave",
        "leave structure", "paid time off", "how many days off",
        "leaves", "leave", "holiday", "vacation", "time off",
    ],
    "ben_food": [
        "food allowance", "cab facility", "travel allowance",
        "do you provide cab", "transport facility", "meal allowance",
        "pick and drop", "is there food",
        "transport", "food", "cafeteria", "cab", "conveyance", "allowance",
    ],
    "ben_other": [
        "stock options", "other benefits", "additional perks",
        "extra perks", "employee benefits", "company benefits",
        "what are the benefits", "what do you offer",
        "any other benefits", "other perks",
        "esop", "gym", "wellness", "laptop", "stock",
        "perks", "benefits",
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

SALARY_SUB_MAP   = {"1": "salary_basic",    "2": "salary_ctc",    "3": "salary_variables", "4": "salary_increment"}
RESP_SUB_MAP     = {"1": "resp_daily",      "2": "resp_skills",   "3": "resp_team",        "4": "resp_growth"}
LOCATION_SUB_MAP = {"1": "loc_city",        "2": "loc_remote",    "3": "loc_travel"}
NOTICE_SUB_MAP   = {"1": "notice_duration", "2": "notice_buyout", "3": "notice_immediate"}
BENEFITS_SUB_MAP = {"1": "ben_insurance",   "2": "ben_leaves",    "3": "ben_food",         "4": "ben_other"}

JD_FIELDS = frozenset(
    list(SALARY_SUB_MAP.values()) +
    list(RESP_SUB_MAP.values()) +
    list(LOCATION_SUB_MAP.values()) +
    list(NOTICE_SUB_MAP.values()) +
    list(BENEFITS_SUB_MAP.values())
)

# Intents that are allowed even after candidate has decided
JD_QUESTION_INTENTS = frozenset(
    list(JD_FIELDS) +
    [f"jd_{f}" for f in JD_FIELDS] +
    [
        "menu_salary", "menu_responsibilities",
        "menu_location", "menu_notice_period",
        "menu_benefits", "back_main",
    ]
)


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


async def resolve_intent(candidate_id: int, message: str) -> str | None:
    normalized = message.strip().lower()

    # Tier 1 — pure Python, no Redis needed
    intent = _match_intent(normalized)
    if intent:
        return intent

    # Main menu numbers — no Redis needed
    if normalized in MAIN_MENU_MAP:
        return MAIN_MENU_MAP[normalized]

    # Tier 2c — natural language topic — no Redis needed
    topic = _detect_topic(normalized)
    if topic:
        return f"jd_{topic}"

    # Only fetch context for sub-menu number resolution
    # ~80% of messages never reach this line
    context = await get_context(candidate_id)

    sub_maps = {
        "salary":           SALARY_SUB_MAP,
        "responsibilities": RESP_SUB_MAP,
        "location":         LOCATION_SUB_MAP,
        "notice_period":    NOTICE_SUB_MAP,
        "benefits":         BENEFITS_SUB_MAP,
    }
    if context in sub_maps and normalized in sub_maps[context]:
        return sub_maps[context][normalized]

    return None