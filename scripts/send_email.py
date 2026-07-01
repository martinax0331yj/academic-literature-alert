from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage


REQUIRED_ENV = ["EMAIL_SENDER", "EMAIL_PASSWORD", "EMAIL_RECEIVER", "SMTP_HOST", "SMTP_PORT"]


def missing_email_env() -> list[str]:
    return [name for name in REQUIRED_ENV if not os.getenv(name)]


def send_email(subject: str, markdown_body: str, html_body: str | None = None, dry_run: bool = False) -> bool:
    missing = missing_email_env()
    if dry_run or missing:
        if missing:
            print(f"Email not sent. Missing environment variables: {', '.join(missing)}")
        else:
            print("Email dry-run enabled. No email sent.")
        print("\n--- EMAIL PREVIEW ---\n")
        print(markdown_body)
        return False

    sender = os.environ["EMAIL_SENDER"]
    receiver = os.environ["EMAIL_RECEIVER"]
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = receiver
    message.set_content(markdown_body)
    if html_body:
        message.add_alternative(html_body, subtype="html")

    host = os.environ["SMTP_HOST"]
    port = int(os.environ["SMTP_PORT"])
    password = os.environ["EMAIL_PASSWORD"]
    with smtplib.SMTP(host, port, timeout=30) as server:
        server.starttls()
        server.login(sender, password)
        server.send_message(message)
    return True
