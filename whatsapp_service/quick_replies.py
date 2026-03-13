from shared.redis_client import redis_client as _redis

# Maps incoming text/number to an intent key

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

NOTICE_SUB_MAP = {
    "1": "notice_duration",
    "duration": "notice_duration",
    "2": "notice_buyout",
    "buyout": "notice_buyout",
    "3": "notice_immediate",
    "immediate": "notice_immediate",
}

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

DECISION_MAP = {
    "yes": "interested",
    "yes i am interested": "interested",
    "interested": "interested",
    "i am interested": "interested",
    "i'm interested": "interested",
    "interested in this role": "interested",
    "yes im interested in this": "interested",
    "yes i am interested in this role": "interested",
    "no": "not_interested",
    "not interested": "not_interested",
    "no thanks": "not_interested",
    "not_interested": "not_interested",
    "not interested in this role": "not_interested",
    "no im not interested in this": "not_interested",
    "no i am not interested in this role": "not_interested",
    "0": "back_main",
    "back": "back_main",
    "main menu": "back_main",
    "menu": "back_main",
    "back to main menu": "back_main",
    "back to main": "back_main",
    "back to menu": "back_main",
}

CONTEXT_TTL = 60 * 60


def set_context(candidate_id, context):
    _redis.set(f"wa_ctx:{candidate_id}", context, ex=CONTEXT_TTL)


def get_context(candidate_id):
    return _redis.get(f"wa_ctx:{candidate_id}") or "main"


def clear_context(candidate_id):
    _redis.delete(f"wa_ctx:{candidate_id}")


def resolve_intent(candidate_id, message):
    normalized = message.strip().lower()
    context = get_context(candidate_id)

    if normalized in DECISION_MAP:
        return DECISION_MAP[normalized]

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

    return MAIN_MENU_MAP.get(normalized)