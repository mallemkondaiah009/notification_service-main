# Maps incoming text/number to an intent key

# ── Main menu ──────────────────────────────────────────────────────────
MAIN_MENU_MAP = {
    "1": "menu_responsibilities",
    "responsibilities": "menu_responsibilities",

    "2": "menu_salary",
    "salary": "menu_salary",
    "ctc": "menu_salary",
    "pay": "menu_salary",

    "3": "menu_notice_period",
    "notice": "menu_notice_period",
    "notice period": "menu_notice_period",

    "4": "menu_location",
    "location": "menu_location",
    "work location": "menu_location",

    "5": "menu_benefits",
    "benefits": "menu_benefits",
    "perks": "menu_benefits",
}

# ── Salary sub-menu ────────────────────────────────────────────────────
SALARY_SUB_MAP = {
    "1": "salary_basic",
    "basic": "salary_basic",
    "basic salary": "salary_basic",

    "2": "salary_ctc",
    "total ctc": "salary_ctc",

    "3": "salary_variables",
    "bonus": "salary_variables",
    "variable": "salary_variables",

    "4": "salary_increment",
    "increment": "salary_increment",
    "hike": "salary_increment",
}

# ── Responsibilities sub-menu ──────────────────────────────────────────
RESP_SUB_MAP = {
    "1": "resp_daily",
    "daily": "resp_daily",
    "tasks": "resp_daily",

    "2": "resp_skills",
    "skills": "resp_skills",
    "requirements": "resp_skills",

    "3": "resp_team",
    "team": "resp_team",
    "reporting": "resp_team",

    "4": "resp_growth",
    "growth": "resp_growth",
    "career": "resp_growth",
}

# ── Location sub-menu ──────────────────────────────────────────────────
LOCATION_SUB_MAP = {
    "1": "loc_city",
    "city": "loc_city",
    "office": "loc_city",

    "2": "loc_remote",
    "remote": "loc_remote",
    "hybrid": "loc_remote",
    "wfh": "loc_remote",

    "3": "loc_travel",
    "travel": "loc_travel",
}

# ── Notice period sub-menu ─────────────────────────────────────────────
NOTICE_SUB_MAP = {
    "1": "notice_duration",
    "duration": "notice_duration",

    "2": "notice_buyout",
    "buyout": "notice_buyout",

    "3": "notice_immediate",
    "immediate": "notice_immediate",
}

# ── Benefits sub-menu ──────────────────────────────────────────────────
BENEFITS_SUB_MAP = {
    "1": "ben_insurance",
    "insurance": "ben_insurance",
    "health": "ben_insurance",

    "2": "ben_leaves",
    "leave": "ben_leaves",
    "leaves": "ben_leaves",

    "3": "ben_food",
    "food": "ben_food",
    "transport": "ben_food",

    "4": "ben_other",
    "other": "ben_other",
    "perks": "ben_other",
}

# ── Yes / No / Back ────────────────────────────────────────────────────
DECISION_MAP = {
    "yes": "interested",
    "yes i am interested": "interested",
    "interested": "interested",
    "i am interested": "interested",
    "i'm interested": "interested",

    "no": "not_interested",
    "not interested": "not_interested",
    "no thanks": "not_interested",
    "not_interested": "not_interested",

    "0": "back_main",
    "back": "back_main",
    "main menu": "back_main",
    "menu": "back_main",
}

# Tracks which sub-menu the candidate is currently in
# Key: candidate_id → current_context
# In production use Redis or DB; here we use in-memory dict
_candidate_context: dict = {}


def set_context(candidate_id, context):
    _candidate_context[candidate_id] = context


def get_context(candidate_id):
    return _candidate_context.get(candidate_id, "main")


def clear_context(candidate_id):
    _candidate_context.pop(candidate_id, None)


def resolve_intent(candidate_id, message):
    """
    Resolves message to an intent based on current context.
    Returns intent string or None (means send to AI).
    """
    normalized = message.strip().lower()
    context = get_context(candidate_id)

    # Always check decisions first (YES/NO/back)
    if normalized in DECISION_MAP:
        return DECISION_MAP[normalized]

    # Context-based sub-menu resolution
    if context == "salary":
        return SALARY_SUB_MAP.get(normalized)

    elif context == "responsibilities":
        return RESP_SUB_MAP.get(normalized)

    elif context == "location":
        return LOCATION_SUB_MAP.get(normalized)

    elif context == "notice_period":
        return NOTICE_SUB_MAP.get(normalized)

    elif context == "benefits":
        return BENEFITS_SUB_MAP.get(normalized)

    # Main menu
    return MAIN_MENU_MAP.get(normalized)