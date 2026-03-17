from .menus import send_main_menu

async def send_initial_whatsapp(candidate) -> None:
    await send_main_menu(candidate)