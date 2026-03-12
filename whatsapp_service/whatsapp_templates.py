from .menus import send_main_menu


def send_initial_whatsapp(candidate):
    """Sends main menu as the first message to candidate."""
    send_main_menu(candidate)