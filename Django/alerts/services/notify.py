"""预警通知：站内消息 + 邮件。

站内通知为本地 AlertNotification 记录；邮件通过 Django SMTP 发送，
未配置 EMAIL_NOTIFY_ENABLED 时降级为站内通知并记录失败原因。
"""
import logging

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from alerts.models import AlertNotification

logger = logging.getLogger(__name__)

_PLATFORM_RECIPIENT = "站内"


def _send_email(recipient: str, subject: str, body: str) -> tuple[bool, str]:
    """发送邮件。返回 (是否成功, 错误信息)。"""
    if not settings.EMAIL_NOTIFY_ENABLED:
        return False, "邮件通知未启用"
    if not recipient:
        return False, "缺少收件人"
    try:
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [recipient],
            fail_silently=False,
        )
        return True, ""
    except Exception as exc:
        logger.warning("alert email to %s failed: %s", recipient, exc)
        return False, str(exc)


def _subject_for(event) -> str:
    level_label = event.get_level_display()
    return f"[舆情预警·{level_label}] {event.reason[:60]}"


def _body_for(event) -> str:
    lines = [
        f"触发规则：{event.rule.name}",
        f"关注等级：{event.get_level_display()}",
        f"触发时间：{event.triggered_at:%Y-%m-%d %H:%M:%S}",
        f"主题：{event.topic.name}",
        "",
        "触发原因：",
        event.reason,
    ]
    if event.matched_posts:
        lines.append("")
        lines.append("相关帖子：")
        for p in event.matched_posts[:10]:
            title = (p.get("snippet") or p.get("title") or "")[:80]
            lines.append(f"- {p.get('post_id', '')} {title} {p.get('url', '')}")
    return "\n".join(lines)


def dispatch_notifications(event):
    """按规则配置的通知渠道发送通知，返回创建的 AlertNotification 列表。"""
    rule = event.rule
    channels = rule.notify_channels or []
    recipients = rule.notify_recipients or []
    created = []

    if not channels:
        # 未配置渠道时，默认至少生成一条站内通知
        note = AlertNotification.objects.create(
            event=event, channel="platform", recipient=_PLATFORM_RECIPIENT,
            status="sent", sent_at=timezone.now(),
        )
        return [note]

    for channel in channels:
        if channel == "platform":
            note = AlertNotification.objects.create(
                event=event, channel="platform", recipient=_PLATFORM_RECIPIENT,
                status="sent", sent_at=timezone.now(),
            )
            created.append(note)
        elif channel == "email":
            for recipient in recipients:
                ok, err = _send_email(recipient, _subject_for(event), _body_for(event))
                note = AlertNotification.objects.create(
                    event=event, channel="email", recipient=recipient,
                    status="sent" if ok else "failed",
                    sent_at=timezone.now() if ok else None,
                    error_message=err or None,
                )
                created.append(note)
                # M13：邮件失败/未启用时回退站内通知，保证收件人总能收到预警
                if not ok:
                    created.append(AlertNotification.objects.create(
                        event=event, channel="platform", recipient=_PLATFORM_RECIPIENT,
                        status="sent", sent_at=timezone.now(),
                        error_message=f"邮件发送失败，已回退站内：{err}" if err else "邮件未启用，已回退站内",
                    ))
    return created
