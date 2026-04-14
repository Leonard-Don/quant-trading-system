"""Notification channel orchestration for alerts and operations."""

from __future__ import annotations

import json
import os
import smtplib
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from src.utils.config import PROJECT_ROOT


class NotificationService:
    """Send alert notifications through dry-run, webhook, email or WeCom webhook."""

    def __init__(self, config_path: Optional[str | Path] = None):
        self.config_path = Path(config_path or PROJECT_ROOT / "data" / "infrastructure" / "notification_channels.json")
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

    def status(self) -> Dict[str, Any]:
        return {
            "channels": self.list_channels(),
            "env": {
                "webhook_url_configured": bool(os.getenv("ALERT_WEBHOOK_URL")),
                "wecom_webhook_configured": bool(os.getenv("WECOM_WEBHOOK_URL")),
                "smtp_configured": bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_FROM")),
            },
        }

    def _read_stored_config(self) -> Dict[str, Any]:
        try:
            if self.config_path.exists():
                return json.loads(self.config_path.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {"channels": []}

    def _write_stored_config(self, payload: Dict[str, Any]) -> None:
        self.config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _public_channel(channel: Dict[str, Any]) -> Dict[str, Any]:
        settings = channel.get("settings") if isinstance(channel.get("settings"), dict) else {}
        masked_settings = {}
        for key, value in settings.items():
            if any(token in str(key).lower() for token in ("url", "token", "secret", "password", "webhook")):
                masked_settings[key] = "***configured***" if value else ""
            else:
                masked_settings[key] = value
        return {
            "id": channel.get("id"),
            "type": channel.get("type", "dry_run"),
            "enabled": bool(channel.get("enabled", True)),
            "label": channel.get("label") or channel.get("id"),
            "settings": masked_settings,
            "source": channel.get("source", "stored"),
        }

    def list_channels(self) -> List[Dict[str, Any]]:
        channels = [
            {"id": "dry_run", "type": "dry_run", "enabled": True, "label": "Dry Run", "source": "builtin"},
        ]
        if os.getenv("ALERT_WEBHOOK_URL"):
            channels.append({"id": "webhook", "type": "webhook", "enabled": True, "label": "Webhook", "source": "env"})
        if os.getenv("WECOM_WEBHOOK_URL"):
            channels.append({"id": "wecom", "type": "wecom", "enabled": True, "label": "企业微信", "source": "env"})
        if os.getenv("SMTP_HOST") and os.getenv("SMTP_FROM"):
            channels.append({"id": "email", "type": "email", "enabled": True, "label": "Email", "source": "env"})
        stored = self._read_stored_config()
        channels.extend(self._public_channel(item) for item in stored.get("channels") or [])
        return channels

    def save_channel(self, channel: Dict[str, Any]) -> Dict[str, Any]:
        channel_id = str(channel.get("id") or "").strip().lower()
        channel_type = str(channel.get("type") or "dry_run").strip().lower()
        if not channel_id:
            raise ValueError("channel id is required")
        if channel_type not in {"dry_run", "webhook", "wecom", "email"}:
            raise ValueError(f"unsupported channel type: {channel_type}")
        if channel_id in {"dry_run", "webhook", "wecom", "email"}:
            channel_id = f"custom_{channel_id}"

        stored = self._read_stored_config()
        channels = [
            item for item in stored.get("channels") or []
            if str(item.get("id") or "").lower() != channel_id
        ]
        normalized = {
            "id": channel_id,
            "type": channel_type,
            "enabled": bool(channel.get("enabled", True)),
            "label": channel.get("label") or channel_id,
            "settings": channel.get("settings") if isinstance(channel.get("settings"), dict) else {},
            "source": "stored",
            "updated_at": datetime.utcnow().isoformat(),
        }
        channels.append(normalized)
        self._write_stored_config({"channels": channels})
        return self._public_channel(normalized)

    def delete_channel(self, channel_id: str) -> Dict[str, Any]:
        normalized_id = str(channel_id or "").strip().lower()
        stored = self._read_stored_config()
        channels = stored.get("channels") or []
        remaining = [
            item for item in channels
            if str(item.get("id") or "").lower() != normalized_id
        ]
        self._write_stored_config({"channels": remaining})
        return {"deleted": len(channels) != len(remaining), "channel_id": normalized_id}

    def _get_stored_channel(self, channel_id: str) -> Optional[Dict[str, Any]]:
        normalized_id = str(channel_id or "").strip().lower()
        for channel in self._read_stored_config().get("channels") or []:
            if str(channel.get("id") or "").lower() == normalized_id:
                return channel
        return None

    def send(self, channel: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        normalized_channel = str(channel or "dry_run").lower()
        enriched = {
            "timestamp": datetime.utcnow().isoformat(),
            "source": payload.get("source", "quant_system"),
            "severity": payload.get("severity", "info"),
            "title": payload.get("title", "Quant notification"),
            "message": payload.get("message", ""),
            "payload": payload,
        }
        if normalized_channel == "webhook":
            return self._send_webhook(os.getenv("ALERT_WEBHOOK_URL"), enriched)
        if normalized_channel == "wecom":
            return self._send_webhook(os.getenv("WECOM_WEBHOOK_URL"), {"msgtype": "markdown", "markdown": {"content": self._wecom_content(enriched)}})
        if normalized_channel == "email":
            return self._send_email(enriched)
        stored_channel = self._get_stored_channel(normalized_channel)
        if stored_channel and stored_channel.get("enabled", True):
            channel_type = str(stored_channel.get("type") or "dry_run").lower()
            settings = stored_channel.get("settings") if isinstance(stored_channel.get("settings"), dict) else {}
            if channel_type == "webhook":
                return self._send_webhook(settings.get("url") or settings.get("webhook_url"), enriched)
            if channel_type == "wecom":
                return self._send_webhook(
                    settings.get("url") or settings.get("webhook_url"),
                    {"msgtype": "markdown", "markdown": {"content": self._wecom_content(enriched)}},
                )
            if channel_type == "email":
                return self._send_email(enriched, settings=settings)
        return {"status": "dry_run", "channel": normalized_channel, "delivered": False, "payload": enriched}

    def _send_webhook(self, url: Optional[str], payload: Dict[str, Any]) -> Dict[str, Any]:
        if not url:
            return {"status": "skipped", "reason": "webhook URL is not configured", "delivered": False}
        response = requests.post(url, json=payload, timeout=10)
        return {
            "status": "sent" if response.ok else "failed",
            "channel": "webhook",
            "delivered": response.ok,
            "status_code": response.status_code,
        }

    def _send_email(self, payload: Dict[str, Any], settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        settings = settings or {}
        host = settings.get("host") or os.getenv("SMTP_HOST")
        sender = settings.get("from") or os.getenv("SMTP_FROM")
        recipient = payload["payload"].get("to") or settings.get("to") or os.getenv("ALERT_EMAIL_TO")
        if not host or not sender or not recipient:
            return {"status": "skipped", "reason": "SMTP_HOST, SMTP_FROM or recipient is missing", "delivered": False}

        message = EmailMessage()
        message["Subject"] = payload["title"]
        message["From"] = sender
        message["To"] = recipient
        message.set_content(f"{payload['message']}\n\n{json.dumps(payload['payload'], ensure_ascii=False, indent=2)}")
        port = int(settings.get("port") or os.getenv("SMTP_PORT", "25"))
        username = settings.get("username") or os.getenv("SMTP_USERNAME")
        password = settings.get("password") or os.getenv("SMTP_PASSWORD")
        use_tls = str(settings.get("use_tls", os.getenv("SMTP_USE_TLS", "true"))).lower() != "false"
        with smtplib.SMTP(host, port, timeout=10) as smtp:
            if username and password:
                if use_tls:
                    smtp.starttls()
                smtp.login(username, password)
            smtp.send_message(message)
        return {"status": "sent", "channel": "email", "delivered": True, "to": recipient}

    def _wecom_content(self, payload: Dict[str, Any]) -> str:
        return f"**{payload['title']}**\n\n> 级别: {payload['severity']}\n\n{payload['message']}"


notification_service = NotificationService()
