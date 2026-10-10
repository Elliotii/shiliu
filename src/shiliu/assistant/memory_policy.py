"""Small deterministic guards around model proposed personal memories."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from calendar import monthrange
from zoneinfo import ZoneInfo
import re


TZ = ZoneInfo("Asia/Shanghai")
_DURATION = re.compile(r"(?:接下来|未来|往后)([一二三四五六七八九十\d]+)(天|周|个月)")
_RELATIVE = re.compile(r"下周|这周|本周|明天|后天")
_UNSUPPORTED_TIME = re.compile(r"下下周|下个月|下月|下季度|明年|月底|月初|过几天|几周|(?:十[一二三四五六七八九]?|两)(?:天|周|个月)|\d{1,2}月(?:\d{1,2}[日号])?")
_CLEAR_TIME = re.compile(r"(?:取消|去掉|不设|不再设|没有|不限).{0,6}(?:期限|截止|到期)|(?:改成|变成|作为).{0,4}(?:长期|持续|永久)|长期")
_CLEAR_DIRECT = re.compile(r"(?:取消|去掉|不设|不再设|没有|不限).{0,6}(?:期限|截止|到期)|(?:改成|变成|作为).{0,4}(?:长期|持续|永久)")
_UNCHANGED_TIME = re.compile(r"(?:日期|时间|期限|截止日|到期日)(?:保持)?不变|只(?:把|改)(?:.{0,30})(?:日期|时间|期限)(?:不变|不动)")
_EXPLICIT_DATE = re.compile(r"(?<!\d)(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})(?:日|号)?(?!\d)")


def forbids_auto_save(text: str) -> bool:
    personal_text = re.sub(r"(?:不要|别|不许|禁止).{0,5}保存这段(?:分析|回答|讨论|知识页)", "", text)
    return bool(re.search(r"(?:不要|别|不许|禁止|无需|仅本次|只在这次).{0,12}(?:保存|记住|记忆|记录)|(?:不要|别).{0,8}存", personal_text))


def anchored_validity(excerpt: str, stated_at: str) -> dict[str, str] | None:
    """Return a preparation window; never reinterpret relative dates at job time."""
    if _UNSUPPORTED_TIME.search(excerpt) or _EXPLICIT_DATE.search(excerpt):
        return None
    durations = list(_DURATION.finditer(excerpt))
    relatives = list(_RELATIVE.finditer(excerpt))
    matches = sorted([*durations, *relatives], key=lambda value: value.start())
    if not matches:
        if re.search(r"[一二三四五六七八九十两百\d]+(?:天|周|个月)", excerpt):
            return None
        return {}
    latest = matches[-1]
    duration = latest if latest.re is _DURATION else None
    try:
        said = datetime.fromisoformat(stated_at.replace("Z", "+00:00")).astimezone(TZ)
    except ValueError:
        return None
    if duration:
        number = duration.group(1)
        if number.isdigit():
            count = int(number)
        elif len(number) == 1 and number in "一二三四五六七八九十":
            count = "一二三四五六七八九十".index(number) + 1
        else:
            return None
        maximum = {"天": 366, "周": 52, "个月": 24}[duration.group(2)]
        if count < 1 or count > maximum:
            return None
        if duration.group(2) == "个月":
            month_index = said.year * 12 + said.month - 1 + count
            year, month_zero = divmod(month_index, 12)
            month = month_zero + 1
            day = min(said.day, monthrange(year, month)[1])
            last = said.date().replace(year=year, month=month, day=day)
        else:
            last = said.date() + timedelta(days=count * (7 if duration.group(2) == "周" else 1))
        end = datetime.combine(last + timedelta(days=1), datetime.min.time(), TZ)
    elif latest.group() == "下周":
        monday = said.date() - timedelta(days=said.weekday()) + timedelta(days=7)
        end = datetime.combine(monday + timedelta(days=7), datetime.min.time(), TZ)
    elif latest.group() in {"这周", "本周"}:
        monday = said.date() - timedelta(days=said.weekday())
        end = datetime.combine(monday + timedelta(days=7), datetime.min.time(), TZ)
    else:
        days = 1 if latest.group() == "明天" else 2
        end = datetime.combine(said.date() + timedelta(days=days + 1), datetime.min.time(), TZ)
    return {
        "expires_at": end.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "validity_note": f"原话：{excerpt[:180]}；按陈述时间 {said.isoformat(timespec='seconds')} 解释",
        "validity_timezone": "Asia/Shanghai",
    }


def time_phrase(text: str) -> str | None:
    matches = sorted([*_DURATION.finditer(text), *_RELATIVE.finditer(text)], key=lambda value: value.start())
    return matches[-1].group() if matches else None


def has_time_reference(text: str) -> bool:
    """Recognize even relative dates that cannot be anchored reliably."""
    return bool(time_phrase(text) or _UNSUPPORTED_TIME.search(text) or _EXPLICIT_DATE.search(text))


def clears_time(text: str) -> bool:
    return bool(_CLEAR_TIME.search(text))


def cancels_time(statement: str, target_text: str) -> bool:
    return bool(_CLEAR_DIRECT.search(statement) or (clears_time(target_text) and not time_phrase(target_text)))


def keeps_time(text: str) -> bool:
    return bool(_UNCHANGED_TIME.search(text))


def requests_time_change(text: str) -> bool:
    for match in re.finditer(r"改到|改期到|推迟到|提前到|延期到|调整到|延后至", text):
        target = text[match.end():match.end() + 30]
        if time_phrase(target) or _EXPLICIT_DATE.search(target) or _UNSUPPORTED_TIME.search(target):
            return True
    return False


def explicit_expiry_has_user_basis(statement: str, expires_at: str) -> bool:
    """A model-supplied deadline must correspond to an absolute user date."""
    try:
        expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        if expiry.tzinfo is None:
            return False
        local_expiry = expiry.astimezone(TZ)
        local_date = local_expiry.date()
    except ValueError:
        return False
    for match in _EXPLICIT_DATE.finditer(statement):
        try:
            said_date = datetime(int(match[1]), int(match[2]), int(match[3])).date()
        except ValueError:
            continue
        time_part = re.match(r"\s*(?:T|在|的)?(\d{1,2}):(\d{2})", statement[match.end():])
        if time_part:
            if (local_date == said_date and local_expiry.hour == int(time_part[1])
                    and local_expiry.minute == int(time_part[2])):
                return True
        elif (local_date in {said_date, said_date + timedelta(days=1)}
              and local_expiry.hour == 0 and local_expiry.minute == 0):
            return True
    return False


def plausible_personal_excerpt(excerpt: str, kind: str) -> bool:
    if re.search(r"(?:视频|作者|字幕|文章|文档|讲者|助手|你建议).{0,12}(?:说|认为|提到|建议)", excerpt):
        return bool(re.search(r"我(?:决定|采纳|选择)|我们(?:决定|采纳)", excerpt))
    if re.search(r"^(?:如果|假设|比如|例如|假如|引用|转述|有人说)|(?:是假设|是例句|只是引用)", excerpt):
        return False
    if re.search(r"我(?:还在|正在)(?:比较|考虑|犹豫)", excerpt):
        return kind == "context"
    if kind == "decision" and not re.search(r"我(?:决定|确定|选|采用|采纳)|我们(?:决定|确定)|就按", excerpt):
        return False
    return bool(re.search(r"我|我们|本人|本项目|这个项目|项目|我的|近期|下周|明天|请记住|今天确定|接下来.{1,8}(?:天|周|月)", excerpt))
