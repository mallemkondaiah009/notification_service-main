import json
import re

from shared.redis_client import redis_context  # DB1 — context + jd_cache

# ── Field keyword map ──────────────────────────────────────────────────

JD_FIELD_KEYWORDS = {
    "salary_basic": [
        "basic salary", "basic pay", "fixed salary", "base salary", "monthly salary",
        "what is the salary", "how much salary", "what will i get", "how much will i get",
        "what is the pay", "what's the pay", "how much do you pay", "monthly pay",
        "monthly income", "fixed pay", "what do you offer", "salary details",
    ],
    "salary_ctc": [
        "ctc", "cost to company", "total compensation", "package", "annual salary",
        "total package", "yearly salary", "annual package", "what is the package",
        "total salary", "how much is the ctc", "what is the ctc", "annual ctc",
        "total ctc", "complete package",
    ],
    "salary_variables": [
        "variable", "bonus", "incentive", "performance pay", "commission",
        "performance bonus", "target bonus", "variable pay", "incentive pay",
        "any bonus", "is there a bonus", "do you give bonus", "what about bonus",
        "sales incentive", "quarterly bonus", "annual bonus",
    ],
    "salary_increment": [
        "increment", "hike", "appraisal", "annual raise", "salary review",
        "salary hike", "salary increase", "performance review", "when is appraisal",
        "how often hike", "yearly increment", "pay raise", "raise",
    ],
    "resp_daily": [
        "responsibilities", "duties", "day-to-day", "daily tasks", "what you will do",
        "key responsibilities", "what will i do", "what is my role", "what is the job",
        "job duties", "what does the job involve", "what is the work",
        "what kind of work", "daily work", "role and responsibilities",
        "what will be my work", "what do i have to do",
    ],
    "resp_skills": [
        "skills", "requirements", "qualifications", "must have", "required skills",
        "tech stack", "what skills", "what do you need", "what are the requirements",
        "what should i know", "what technologies", "what tools", "skill set",
        "technical skills", "what experience", "years of experience", "experience required",
    ],
    "resp_team": [
        "team", "reporting", "manager", "collaborate", "work with",
        "who will i report to", "team size", "how many people", "who is my manager",
        "reporting structure", "who do i report", "team structure",
        "department", "who is the boss",
    ],
    "resp_growth": [
        "growth", "career", "promotion", "learning", "development", "opportunity",
        "career growth", "career path", "growth opportunities", "can i grow",
        "promotion policy", "learning opportunities", "training", "upskill",
        "career development", "future scope", "is there growth",
    ],
    "loc_city": [
        "location", "city", "office location", "based in", "work from",
        "where is the office", "which city", "where is the job", "office address",
        "where do i have to work", "which location", "job location",
        "where is it located", "office city",
    ],
    "loc_remote": [
        "remote", "hybrid", "work from home", "wfh", "onsite",
        "can i work from home", "is it remote", "is there wfh", "work from anywhere",
        "do i have to come to office", "is it hybrid", "work mode",
        "office or home", "flexible work",
    ],
    "loc_travel": [
        "travel", "on-site visits", "client visits", "relocation",
        "do i have to travel", "is there travel", "travel requirement",
        "client travel", "field work", "site visits", "travel involved",
    ],
    "notice_duration": [
        "notice period", "notice", "serving notice",
        "how long is the notice", "what is the notice period",
        "how many days notice", "joining time", "when can i join",
        "how soon can i join", "notice period duration",
    ],
    "notice_buyout": [
        "buyout", "buy out notice", "notice buyout",
        "can you buy out my notice", "will you pay for notice",
        "notice period buyout", "can i get buyout",
    ],
    "notice_immediate": [
        "immediate joiner", "immediate joining", "joining immediately", "can join",
        "i can join immediately", "available immediately", "immediate availability",
        "can join right away", "no notice period",
    ],
    "ben_insurance": [
        "health insurance", "medical", "insurance", "hospitalization",
        "medical benefits", "health cover", "is there insurance",
        "medical insurance", "family insurance", "health benefits",
        "do you provide insurance", "mediclaim",
    ],
    "ben_leaves": [
        "leave", "paid leave", "casual leave", "sick leave", "holidays",
        "how many leaves", "leave policy", "annual leave", "how many holidays",
        "leave structure", "vacation", "time off", "paid time off",
        "how many days off", "leave days",
    ],
    "ben_food": [
        "food", "cafeteria", "transport", "cab", "allowance",
        "is there food", "do you provide cab", "transport facility",
        "meal allowance", "food allowance", "cab facility", "travel allowance",
        "conveyance", "pick and drop",
    ],
    "ben_other": [
        "perks", "benefits", "gym", "wellness", "laptop", "stock", "esop",
        "what are the benefits", "other benefits", "additional perks",
        "what do you offer", "company benefits", "employee benefits",
        "any other benefits", "extra perks", "stock options",
    ],
}

FRIENDLY_LABELS = {
    "salary_basic":     "Basic Salary",
    "salary_ctc":       "Total CTC",
    "salary_variables": "Variable / Bonus",
    "salary_increment": "Increment Policy",
    "resp_daily":       "Daily Responsibilities",
    "resp_skills":      "Required Skills",
    "resp_team":        "Team & Reporting",
    "resp_growth":      "Growth Opportunities",
    "loc_city":         "Office Location",
    "loc_remote":       "Remote / Hybrid Policy",
    "loc_travel":       "Travel Requirements",
    "notice_duration":  "Notice Period Duration",
    "notice_buyout":    "Notice Buyout Policy",
    "notice_immediate": "Immediate Joining",
    "ben_insurance":    "Health Insurance",
    "ben_leaves":       "Leave Policy",
    "ben_food":         "Food & Transport",
    "ben_other":        "Other Perks",
}

VOICE_TEMPLATES = {
    "salary_basic":     "Regarding the basic salary, {answer}",
    "salary_ctc":       "The total CTC for this role is, {answer}",
    "salary_variables": "Regarding variable pay and bonuses, {answer}",
    "salary_increment": "Regarding increment and appraisal policy, {answer}",
    "resp_daily":       "The key responsibilities for this role are, {answer}",
    "resp_skills":      "The required skills for this position are, {answer}",
    "resp_team":        "Regarding the team structure, {answer}",
    "resp_growth":      "Regarding career growth opportunities, {answer}",
    "loc_city":         "The office location is, {answer}",
    "loc_remote":       "Regarding the work mode, {answer}",
    "loc_travel":       "Regarding travel requirements, {answer}",
    "notice_duration":  "The notice period for this role is, {answer}",
    "notice_buyout":    "Regarding notice buyout, {answer}",
    "notice_immediate": "Regarding immediate joining, {answer}",
    "ben_insurance":    "Regarding health insurance, {answer}",
    "ben_leaves":       "Regarding the leave policy, {answer}",
    "ben_food":         "Regarding food and transport benefits, {answer}",
    "ben_other":        "Regarding other perks and benefits, {answer}",
}

# ── Private pure-Python helpers (no I/O — stay sync) ──────────────────

def _normalize_speech(text: str) -> str:
    text = text.lower().strip()
    for filler in ["um", "uh", "like", "you know", "actually", "basically", "so", "well"]:
        text = re.sub(rf"\b{filler}\b", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _clean_for_voice(text: str) -> str:
    text = re.sub(r"\*+", "", text)
    text = re.sub(r"_+", "", text)
    text = re.sub(r"#+\s*", "", text)
    text = re.sub(r"^\s*[-•]\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n+", ". ", text)
    text = re.sub(r"\.\s*\.", ".", text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_answer_sync(button_id: str, job_description: str) -> tuple[str, str | None]:
    """
    Pure-Python JD text scan — no I/O, deliberately sync.
    Used internally by both the sync extract_answer() and async cache builder.
    """
    keywords = JD_FIELD_KEYWORDS.get(button_id, [])
    label    = FRIENDLY_LABELS.get(button_id, button_id.replace("_", " ").title())

    if not keywords:
        return label, None

    lines        = job_description.split("\n")
    result_lines = []
    capturing    = False

    for line in lines:
        line_lower = line.lower().strip()

        if any(kw in line_lower for kw in keywords):
            capturing = True
            result_lines.append(line.strip())
            continue

        if capturing:
            if line.strip() and (
                line.strip().endswith(":")
                or line.strip().isupper()
                or (len(line.strip()) > 3 and line.strip()[0].isupper() and line.strip().endswith(":"))
            ):
                break
            if line.strip():
                result_lines.append(line.strip())
            if len(result_lines) >= 5:
                break

    if result_lines:
        return label, "\n".join(result_lines)

    # fallback — first line that contains any keyword
    for line in lines:
        if any(kw in line.lower() for kw in keywords):
            return label, line.strip()

    return label, None


def _match_speech_to_field_sync(speech: str) -> str | None:
    """Pure-Python keyword scorer — sync, no I/O."""
    normalized = _normalize_speech(speech)
    scores = {
        button_id: sum(1 for kw in keywords if kw in normalized)
        for button_id, keywords in JD_FIELD_KEYWORDS.items()
    }
    scores = {k: v for k, v in scores.items() if v > 0}
    return max(scores, key=scores.get) if scores else None


# ── Public sync API (used by call_service / voice handler) ────────────

def extract_answer(button_id: str, job_description: str) -> tuple[str, str | None]:
    """Sync wrapper — kept for call_service compatibility."""
    return _extract_answer_sync(button_id, job_description)


def match_speech_to_field(speech: str) -> str | None:
    """Sync wrapper — kept for call_service compatibility."""
    return _match_speech_to_field_sync(speech)


# ── Async Redis cache (DB1) ────────────────────────────────────────────

async def cache_jd_answers(candidate_id: int, job_description: str) -> None:
    """
    Pre-computes voice-ready answers for every JD field and stores
    them in Redis DB1 as a single JSON blob (TTL 24 h).
    Called once after a candidate is notified.
    """
    answers: dict = {}

    for button_id in JD_FIELD_KEYWORDS:
        label, answer = _extract_answer_sync(button_id, job_description)
        if answer:
            clean    = _clean_for_voice(answer)
            template = VOICE_TEMPLATES.get(button_id, "{answer}")
            answers[button_id] = {
                "label":  label,
                "spoken": template.format(answer=clean),
            }

    await redis_context.set(
        f"jd_cache:{candidate_id}",
        json.dumps(answers),
        ex=60 * 60 * 24,
    )


async def get_cached_answer(candidate_id: int, speech: str) -> tuple[str | None, str | None]:
    """
    Looks up a pre-cached voice answer from Redis DB1.
    Returns (label, spoken_text) or (None, None) if not found.
    """
    try:
        cached = await redis_context.get(f"jd_cache:{candidate_id}")
        if not cached:
            return None, None

        answers   = json.loads(cached)
        button_id = _match_speech_to_field_sync(speech)

        if not button_id or button_id not in answers:
            return None, None

        entry = answers[button_id]
        return entry["label"], entry["spoken"]

    except Exception:
        return None, None


async def invalidate_jd_cache(candidate_id: int) -> None:
    """Deletes the cached JD answers for a candidate (e.g. on JD update)."""
    await redis_context.delete(f"jd_cache:{candidate_id}")