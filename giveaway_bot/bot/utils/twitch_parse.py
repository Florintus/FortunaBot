import re


def normalize_twitch_channel_login(raw: str | None) -> str:
    """
    Приводит ввод к логину канала Twitch (нижний регистр, без домена и протокола).
    Примеры: https://www.twitch.tv/florintus → florintus, twitch.tv/x → x
    """
    if raw is None:
        return ""
    s = str(raw).strip()
    if not s:
        return ""
    s = s.strip("/")
    s = s.lstrip("@")
    low = s.lower()
    m = re.search(r"(?:https?://)?(?:www\.)?twitch\.tv/([^/?#]+)", low)
    if m:
        return m.group(1).lower()
    part = s.split("/")[0].split("?")[0].split("#")[0]
    return part.strip().lstrip("@").lower()
