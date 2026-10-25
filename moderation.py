# -*- coding: utf-8 -*-
"""Group moderation rules: no links, no photos/videos for members.

Allowed to post links/media: the group admins (including @MaynaDz) and bots.
Everything here is pure logic (plus one Telegram call to list admins), so it is easy to test.
"""
import logging
import os
import re
import time

logger = logging.getLogger("mayna-assistant")

ADMIN_USERNAME = (os.getenv("ADMIN_USERNAME", "MaynaDz").strip().lstrip("@")) or "MaynaDz"
ADMIN_MENTION = "@" + ADMIN_USERNAME

# Stickers and GIFs count as images/videos. Set to False to allow stickers.
BLOCK_STICKERS = True

LINK_WARNING = "ممنوع نشر الروابط في المجموعة."
MEDIA_WARNING = "ممنوع نشر الصور والفيديوهات في المجموعة."
WARNING_EMOJI = "⚠️🚫"
WARNING_LIFETIME_SECONDS = 20     # the warning disappears by itself so the group stays clean
WARNING_THROTTLE_SECONDS = 30     # one warning per member per 30 s (albums = many messages)

_INVISIBLE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]")

# explicit link starts: http(s)://, www., tg://, t.me/ (also written "t . me /"), telegram.me/
_URL_START = re.compile(
    r"(?:\b(?:https?|ftp)\s*:\s*//|\bwww\s*\.|\btg://|(?<![\w.])(?:t|telegram)\s*\.\s*me\s*/)",
    re.IGNORECASE,
)
# bare domains such as example.com, mayna.dz/xyz (not preceded by @ or a word char, so emails/mentions pass)
_BARE_DOMAIN = re.compile(
    r"(?<![\w@.\-])[a-z0-9](?:[a-z0-9\-]{0,62}[a-z0-9])?(?:\.[a-z0-9\-]{1,63})*\."
    r"(?:com|net|org|info|io|me|dz|fr|app|xyz|site|online|shop|store|link|gl|club|top|biz|live|page|click|vip|cfd|sbs)"
    r"(?![\w\-])",
    re.IGNORECASE,
)

_LINK_ENTITY_TYPES = {"url", "text_link"}
_VIDEO_EXT = (".mp4", ".mov", ".mkv", ".avi", ".webm", ".3gp", ".m4v", ".mpeg", ".mpg", ".wmv", ".flv", ".gif")
_IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".bmp", ".tif", ".tiff", ".avif")


def has_link(message) -> bool:
    """True if the message text/caption contains any link (clickable, hidden behind text, or typed)."""
    entities = list(getattr(message, "entities", None) or []) + list(getattr(message, "caption_entities", None) or [])
    for ent in entities:
        if str(getattr(ent, "type", "")).lower() in _LINK_ENTITY_TYPES:
            return True
    text = getattr(message, "text", None) or getattr(message, "caption", None) or ""
    text = _INVISIBLE.sub("", text)
    return bool(_URL_START.search(text) or _BARE_DOMAIN.search(text))


def blocked_media(message) -> bool:
    """True for any photo, image file, video, video note, GIF/animation (and stickers if BLOCK_STICKERS)."""
    if getattr(message, "photo", None):
        return True
    if getattr(message, "video", None) or getattr(message, "video_note", None) or getattr(message, "animation", None):
        return True
    if BLOCK_STICKERS and getattr(message, "sticker", None):
        return True
    document = getattr(message, "document", None)
    if document is not None:
        mime = getattr(document, "mime_type", None)
        mime = mime.lower() if isinstance(mime, str) else ""
        if mime.startswith(("image/", "video/")):
            return True
        name = getattr(document, "file_name", None)
        name = name.lower() if isinstance(name, str) else ""
        if name.endswith(_IMAGE_EXT + _VIDEO_EXT):
            return True
    return False


# ---------------------------------------------------------------------------
# Who is an admin?
# ---------------------------------------------------------------------------

_ADMIN_CACHE = {}  # chat_id -> (expires_at, {user_id, ...})
_ADMIN_CACHE_SECONDS = 300


def is_admin_username(user) -> bool:
    return bool(user) and (getattr(user, "username", None) or "").lower() == ADMIN_USERNAME.lower()


async def is_admin(context, chat, message) -> bool:
    """True for @MaynaDz, any group administrator/owner, anonymous admins, and the linked channel's posts.
    Never raises: if Telegram cannot be asked, only the username check applies."""
    sender_chat = getattr(message, "sender_chat", None)
    if sender_chat is not None and getattr(sender_chat, "id", None) == getattr(chat, "id", None):
        return True  # admin posting anonymously as the group
    if getattr(message, "is_automatic_forward", False):
        return True  # the linked channel's post mirrored into the group
    user = getattr(message, "from_user", None)
    if user is None:
        return False
    if is_admin_username(user):
        return True
    now = time.time()
    cached = _ADMIN_CACHE.get(chat.id)
    if cached and cached[0] > now:
        return user.id in cached[1]
    try:
        admins = await context.bot.get_chat_administrators(chat.id)
        ids = {a.user.id for a in admins}
        _ADMIN_CACHE[chat.id] = (now + _ADMIN_CACHE_SECONDS, ids)
        return user.id in ids
    except Exception as exc:
        logger.warning("Could not read the admin list: %s", type(exc).__name__)
        return user.id in (cached[1] if cached else set())


def is_main_admin(message) -> bool:
    """True only for @MaynaDz himself (the account, or him posting anonymously as the group / via the
    linked channel). Other group administrators are NOT included: the bot answers them like any member."""
    if getattr(message, "is_automatic_forward", False):
        return True  # the channel's own post mirrored into the group
    # Anonymous admins (sender_chat == the group) cannot be told apart: any admin, marketers included, may
    # post that way. They are answered unless IGNORE_ANONYMOUS_ADMIN=1.
    sender_chat = getattr(message, "sender_chat", None)
    chat = getattr(message, "chat", None)
    if (os.getenv("IGNORE_ANONYMOUS_ADMIN", "").strip() == "1" and sender_chat is not None
            and chat is not None and getattr(sender_chat, "id", None) == getattr(chat, "id", None)):
        return True
    return is_admin_username(getattr(message, "from_user", None))


async def reply_is_to_admin(context, chat, message) -> bool:
    """True if this message answers one of @MaynaDz's messages (he is already handling it)."""
    target = getattr(message, "reply_to_message", None)
    if target is None:
        return False
    return is_main_admin(target)
