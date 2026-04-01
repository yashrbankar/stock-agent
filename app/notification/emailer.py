import logging
import smtplib
from email.message import EmailMessage

from app.config import get_settings


logger = logging.getLogger(__name__)


class EmailNotifier:
    def __init__(self) -> None:
        self.settings = get_settings()

    def send(self, subject: str, body: str, *, html_body: str | None = None) -> None:
        if not all(
            [
                self.settings.smtp_host,
                self.settings.smtp_username,
                self.settings.smtp_password,
                self.settings.email_from,
                self.settings.email_to,
            ]
        ):
            logger.info("SMTP is not fully configured; skipping email notification.")
            return

        recipients = self.settings.email_to

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.settings.email_from
        message["To"] = ", ".join(recipients)
        message.set_content(body)
        if html_body:
            message.add_alternative(html_body, subtype="html")

        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=30) as server:
            server.starttls()
            server.login(self.settings.smtp_username, self.settings.smtp_password)
            server.send_message(message)

        logger.info("Email report sent to %s", recipients)
