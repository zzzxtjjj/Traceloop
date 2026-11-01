"""SMTP delivery with explicit configuration failure and no credential logging."""

import os
import smtplib
import ssl
from email.message import EmailMessage


def mail_configured():
    return bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_FROM"))


def send_verification_email(address, code):
    if not mail_configured():
        raise ValueError("邮件服务待配置，未发送验证码。请联系项目负责人。")
    message = EmailMessage()
    message["From"] = os.environ["SMTP_FROM"]
    message["To"] = address
    message["Subject"] = "BL TradeLoop 邮箱验证码"
    message.set_content(f"您的验证码为 {code}，15 分钟内有效。请勿向他人透露。")
    try:
        with smtplib.SMTP(
            os.environ["SMTP_HOST"], int(os.getenv("SMTP_PORT", "587")), timeout=15
        ) as client:
            client.starttls(context=ssl.create_default_context())
            if os.getenv("SMTP_USERNAME"):
                client.login(os.environ["SMTP_USERNAME"], os.environ.get("SMTP_PASSWORD", ""))
            client.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise ValueError("邮件发送失败，请稍后重试或联系负责人检查配置。") from exc
