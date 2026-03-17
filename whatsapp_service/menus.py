from .services import send_text_message

MAIN_MENU_TEMPLATE = """👋 Hello {name}!

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

SALARY_MENU_TEMPLATE = """💰 *Salary Details*

Reply with a number:

1️⃣  Basic Salary
2️⃣  Total CTC
3️⃣  Variable / Bonus
4️⃣  Increment Policy

0️⃣  Back to Main Menu"""

RESPONSIBILITIES_MENU_TEMPLATE = """📋 *Responsibilities*

Reply with a number:

1️⃣  Daily Tasks
2️⃣  Required Skills
3️⃣  Team & Reporting
4️⃣  Growth Opportunities

0️⃣  Back to Main Menu"""

LOCATION_MENU_TEMPLATE = """📍 *Work Location*

Reply with a number:

1️⃣  Office City
2️⃣  Remote / Hybrid Policy
3️⃣  Travel Requirements

0️⃣  Back to Main Menu"""

NOTICE_MENU_TEMPLATE = """📅 *Notice Period*

Reply with a number:

1️⃣  Notice Duration
2️⃣  Notice Buyout
3️⃣  Immediate Joiners

0️⃣  Back to Main Menu"""

BENEFITS_MENU_TEMPLATE = """🎁 *Benefits & Perks*

Reply with a number:

1️⃣  Health Insurance
2️⃣  Leave Policy
3️⃣  Food & Transport
4️⃣  Other Perks

0️⃣  Back to Main Menu"""

INTEREST_PROMPT = """{answer}

─────────────────
Are you interested in this position?

✅ Reply *YES* — I'm Interested
❌ Reply *NO* — Not Interested
0️⃣ Reply *0* — Back to Main Menu"""


async def send_main_menu(candidate) -> None:
    await send_text_message(
        candidate.phone,
        MAIN_MENU_TEMPLATE.format(name=candidate.full_name, role=candidate.role_name),
    )

async def send_salary_menu(candidate) -> None:
    await send_text_message(candidate.phone, SALARY_MENU_TEMPLATE)

async def send_responsibilities_menu(candidate) -> None:
    await send_text_message(candidate.phone, RESPONSIBILITIES_MENU_TEMPLATE)

async def send_location_menu(candidate) -> None:
    await send_text_message(candidate.phone, LOCATION_MENU_TEMPLATE)

async def send_notice_period_menu(candidate) -> None:
    await send_text_message(candidate.phone, NOTICE_MENU_TEMPLATE)

async def send_benefits_menu(candidate) -> None:
    await send_text_message(candidate.phone, BENEFITS_MENU_TEMPLATE)

async def send_interest_buttons(candidate, answer: str) -> None:
    await send_text_message(candidate.phone, INTEREST_PROMPT.format(answer=answer))