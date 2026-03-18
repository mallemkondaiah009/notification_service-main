from whatsapp_service.services import send_text_message
from whatsapp_service.menu_text import main_menu_text


async def send_initial_whatsapp(candidate) -> None:
    """Sends main menu as the first message to candidate."""
    await send_text_message(
        candidate.phone,
        main_menu_text(candidate.full_name, candidate.role_name),
    )