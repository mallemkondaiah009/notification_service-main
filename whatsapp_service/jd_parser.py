"""
Extracts specific answers from the job description based on the button ID clicked.
"""

JD_FIELD_KEYWORDS = {
    # Salary
    "salary_basic":     ["basic salary", "basic pay", "fixed salary", "base salary", "monthly salary"],
    "salary_ctc":       ["ctc", "cost to company", "total compensation", "package", "annual salary"],
    "salary_variables": ["variable", "bonus", "incentive", "performance pay", "commission"],
    "salary_increment": ["increment", "hike", "appraisal", "annual raise", "salary review"],

    # Responsibilities
    "resp_daily":       ["responsibilities", "duties", "day-to-day", "daily tasks", "what you will do", "key responsibilities"],
    "resp_skills":      ["skills", "requirements", "qualifications", "must have", "required skills", "tech stack"],
    "resp_team":        ["team", "reporting", "manager", "collaborate", "work with"],
    "resp_growth":      ["growth", "career", "promotion", "learning", "development", "opportunity"],

    # Location
    "loc_city":         ["location", "city", "office location", "based in", "work from"],
    "loc_remote":       ["remote", "hybrid", "work from home", "wfh", "onsite"],
    "loc_travel":       ["travel", "on-site visits", "client visits", "relocation"],

    # Notice Period
    "notice_duration":  ["notice period", "notice", "serving notice"],
    "notice_buyout":    ["buyout", "buy out notice", "notice buyout"],
    "notice_immediate": ["immediate joiner", "immediate joining", "joining immediately", "can join"],

    # Benefits
    "ben_insurance":    ["health insurance", "medical", "insurance", "hospitalization"],
    "ben_leaves":       ["leave", "paid leave", "casual leave", "sick leave", "holidays"],
    "ben_food":         ["food", "cafeteria", "transport", "cab", "allowance"],
    "ben_other":        ["perks", "benefits", "gym", "wellness", "laptop", "stock", "esop"],
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


def extract_answer(button_id, job_description):
    """
    Returns (label, answer) extracted from JD for the given button_id.
    Returns (label, None) if not found.
    """
    keywords = JD_FIELD_KEYWORDS.get(button_id, [])
    label = FRIENDLY_LABELS.get(button_id, button_id.replace("_", " ").title())

    if not keywords:
        return label, None

    lines = job_description.split("\n")
    result_lines = []
    capturing = False

    for line in lines:
        line_lower = line.lower().strip()

        if any(kw in line_lower for kw in keywords):
            capturing = True
            result_lines.append(line.strip())
            continue

        if capturing:
            # Stop at next section header
            if line.strip() and (
                line.strip().endswith(":") or
                line.strip().isupper() or
                (len(line.strip()) > 3 and line.strip()[0].isupper() and line.strip().endswith(":"))
            ):
                break
            if line.strip():
                result_lines.append(line.strip())
            # Capture max 5 lines per section
            if len(result_lines) >= 5:
                break

    if result_lines:
        return label, "\n".join(result_lines)

    # Fallback — return the line containing the keyword
    for line in lines:
        if any(kw in line.lower() for kw in keywords):
            return label, line.strip()

    return label, None
