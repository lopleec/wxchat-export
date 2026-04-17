from __future__ import annotations

import html
import json
import re
from datetime import datetime

TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"[ \t]+")
APPMSG_TYPE_RE = re.compile(r"<appmsg\b.*?<type>(\d+)</type>.*?</appmsg>", re.I | re.S)

LOCAL_TYPE_PLACEHOLDERS = {
    3: ("image", "[图片]"),
    34: ("voice", "[语音消息]"),
    42: ("contact_card", "[名片]"),
    43: ("video", "[视频]"),
    47: ("emoji", "[动画表情]"),
    48: ("location", "[位置]"),
    50: ("call", "[通话]"),
    81604378673: ("chat_history", "[聊天记录]"),
    154618822705: ("mini_program", "[小程序]"),
    244813135921: ("quote", "[引用消息]"),
    266287972401: ("pat", "[拍一拍]"),
    8594229559345: ("red_packet", "[红包]"),
    8589934592049: ("transfer", "[转账]"),
    34359738417: ("file", "[文件]"),
    103079215153: ("file", "[文件]"),
    25769803825: ("file", "[文件]"),
}

APPMSG_TYPE_PLACEHOLDERS = {
    3: ("music", "[音乐]"),
    5: ("link", "[链接卡片]"),
    6: ("file", "[文件]"),
    19: ("chat_history", "[聊天记录]"),
    33: ("mini_program", "[小程序]"),
    36: ("mini_program", "[小程序]"),
    49: ("link", "[链接卡片]"),
    57: ("quote", "[引用消息]"),
    87: ("announcement", "[群公告]"),
    2000: ("transfer", "[转账]"),
    2001: ("red_packet", "[红包]"),
}


def sanitize_filename_component(value: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", value).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:120] or "session"


def clean_text_message(value: str) -> str:
    if not value:
        return ""
    text = html.unescape(value).replace("\r\n", "\n").replace("\r", "\n")
    return text.strip()


def clean_system_message(value: str) -> str:
    if not value:
        return "[系统消息]"
    text = html.unescape(value)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = TAG_RE.sub("", text)
    text = WHITESPACE_RE.sub(" ", text)
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(line for line in lines if line)
    return text or "[系统消息]"


def extract_appmsg_type(message_content: str, compress_content: str = "") -> int | None:
    for raw in (message_content, compress_content):
        if not raw:
            continue
        decoded = html.unescape(raw)
        match = APPMSG_TYPE_RE.search(decoded)
        if match:
            return int(match.group(1))
        if "<appmsg>" in decoded or "<type>" in decoded:
            fallback = re.search(r"<type>(\d+)</type>", decoded)
            if fallback:
                return int(fallback.group(1))
    return None


def classify_message(local_type: int, message_content: str, compress_content: str = "") -> tuple[str, str]:
    if local_type == 1:
        text = clean_text_message(message_content)
        return "text", text or "[文本消息]"
    if local_type == 10000:
        return "system", clean_system_message(message_content)

    appmsg_type = None
    if local_type == 49 or "<appmsg" in html.unescape(message_content or ""):
        appmsg_type = extract_appmsg_type(message_content, compress_content)
        if appmsg_type is not None and appmsg_type in APPMSG_TYPE_PLACEHOLDERS:
            return APPMSG_TYPE_PLACEHOLDERS[appmsg_type]
        return "appmsg", "[链接卡片]"

    if local_type in LOCAL_TYPE_PLACEHOLDERS:
        return LOCAL_TYPE_PLACEHOLDERS[local_type]
    return "unknown", "[未知消息]"


def format_timestamp(timestamp: int) -> str:
    if not timestamp:
        return "1970-01-01 00:00:00"
    value = timestamp / 1000 if timestamp > 10_000_000_000 else timestamp
    return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M:%S")


def json_dumps(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)
