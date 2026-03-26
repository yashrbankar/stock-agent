import logging

from app.config import get_settings


logger = logging.getLogger(__name__)


class WhatsAppNotifier:
    def __init__(self) -> None:
        self.settings = get_settings()

    def send(self, body: str) -> None:
        if not all(
            [
                self.settings.twilio_account_sid,
                self.settings.twilio_auth_token,
                self.settings.twilio_from,
                self.settings.twilio_to,
            ]
        ):
            logger.info("Twilio WhatsApp is not configured; skipping WhatsApp notification.")
            return

        logger.info(
            "WhatsApp notification requested but Twilio client dependency is not installed. "
            "Add the Twilio SDK if you want to enable this path."
        )
