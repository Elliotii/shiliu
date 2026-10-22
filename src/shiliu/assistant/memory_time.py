"""Bounded time interpretation: an event is not a Memory expiry."""
from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timedelta, timezone
import json
import re
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Asia/Shanghai')
TOKEN = re.compile(r'20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}(?:日|号)?|20\d{2}年\d{1,2}月|(?:明年|今年)的?\d{1,2}月|(?:明年|今年)(?:年初|年底)?|下+个?月|(?<!\d)\d{1,2}月(?:\d{1,2}[日号])?|下+周|本周|这周|明天|后天|月底|月初|(?:接下来|未来|往后)[一二三四五六七八九十两\d]+(?:天|周|个月)|过段时间|过一阵|过几天|近期|以后|到时候')
VALIDITY = re.compile(r'(?:记忆|决定|约束|限制|规则|要求|设置)(?:的)?(?:有效期|适用期)|(?:这条|这个|这项|本条|该条|此条|该项|此项|当前)(?:记忆|决定|约束|限制|规则|要求|设置).*(?:有效|适用|失效|到期)(?:了)?\s*$')


def _number(raw: str) -> int:
    if raw.isdigit():
        return int(raw)
    if raw == '两':
        return 2
    digits = '零一二三四五六七八九'
    if '十' in raw:
        a, b = raw.split('十', 1)
        return (digits.index(a) if a else 1) * 10 + (digits.index(b) if b else 0)
    return digits.index(raw)


def _resolve(word: str, said: datetime) -> tuple[str, str | None, str | None]:
    day = said.date()
    if re.fullmatch(r'20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}(?:日|号)?', word):
        year, month, date = map(int, re.findall(r'\d+', word))
        return 'day', day.replace(year=year, month=month, day=date).isoformat(), None
    if re.fullmatch(r'下+个?月', word):
        y, m = divmod(day.year * 12 + day.month - 1 + word.count('下'), 12)
        return 'month', f'{y:04d}-{m + 1:02d}', None
    absolute_month = re.fullmatch(r'(20\d{2})年(\d{1,2})月', word)
    if absolute_month:
        y, m = map(int, absolute_month.groups())
        day.replace(year=y, month=m, day=1)
        return 'month', f'{y:04d}-{m:02d}', None
    qualified_month = re.fullmatch(r'(明年|今年)的?(\d{1,2})月', word)
    if qualified_month:
        y, m = day.year + int(qualified_month[1] == '明年'), int(qualified_month[2])
        day.replace(year=y, month=m, day=1)
        return 'month', f'{y:04d}-{m:02d}', None
    if word.startswith(('明年', '今年')):
        year = day.year + int(word.startswith('明年'))
        return 'year_part', f'{year}{word[2:]}', None
    match = re.fullmatch(r'(\d{1,2})月(?:(\d{1,2})[日号])?', word)
    if match:
        month = int(match[1])
        day.replace(month=month, day=int(match[2] or 1))  # validate
        return ('day', f'{day.year:04d}-{month:02d}-{int(match[2]):02d}', None) if match[2] else ('month', f'{day.year:04d}-{month:02d}', None)
    if re.fullmatch(r'下+周|本周|这周', word):
        monday = day - timedelta(days=day.weekday()) + timedelta(days=7 * word.count('下'))
        year, week, _ = monday.isocalendar()
        return 'week', f'{year}-W{week:02d}', None
    if word in {'明天', '后天'}:
        return 'day', (day + timedelta(days=1 if word == '明天' else 2)).isoformat(), None
    if word in {'月底', '月初'}:
        return 'day', day.replace(day=monthrange(day.year, day.month)[1] if word == '月底' else 1).isoformat(), None
    duration = re.fullmatch(r'(?:接下来|未来|往后)([一二三四五六七八九十两\d]+)(天|周|个月)', word)
    if duration:
        count = _number(duration[1])
        if not 0 < count <= 366:
            return 'vague', None, None
        if duration[2] == '个月':
            y, m = divmod(day.year * 12 + day.month - 1 + count, 12)
            end = day.replace(year=y, month=m + 1, day=min(day.day, monthrange(y, m + 1)[1]))
        else:
            end = day + timedelta(days=count * (7 if duration[2] == '周' else 1))
        return 'range', day.isoformat(), end.isoformat()
    return 'vague', None, None


def time_context(statement: str, stated_at: str, source_message_id: str | None = None,
                 timezone_name: str = 'Asia/Shanghai') -> dict:
    said = datetime.fromisoformat(stated_at.replace('Z', '+00:00'))
    if said.tzinfo is None:
        raise ValueError('memory_time_requires_timezone')
    zone = ZoneInfo(timezone_name)
    said = said.astimezone(zone)
    events = []
    for match in TOKEN.finditer(statement):
        # Validity belongs to its own clause, not a neighbouring event.
        clause = re.split(r'[，。；;,\n]', statement[:match.start()])[-1] + re.split(r'[，。；;,\n]', statement[match.start():])[0]
        if VALIDITY.search(clause):
            continue
        word = match.group()
        try:
            precision, value, end = _resolve(word, said)
        except (ValueError, OverflowError):
            precision, value, end = 'vague', None, None
        relation = 'period' if precision == 'range' else 'start' if re.match(r'\s*(?:开始|起)', statement[match.end():]) else 'target'
        event = dict(relation=relation, expression=word, precision=precision, value=value)
        if end:
            event['end_value'] = end
        events.append(event)
        if len(events) == 2:
            break
    return dict(stated_at=said.astimezone(timezone.utc).isoformat(timespec='seconds'),
                source_message_id=source_message_id, timezone=timezone_name,
                source_excerpt=statement[:1000], events=events)


def event_signature(context: dict) -> str:
    values = [{k: event.get(k) for k in ('relation', 'precision', 'value', 'end_value')}
              | ({'expression': event.get('expression')} if not event.get('value') else {})
              for event in context.get('events', [])]
    return json.dumps(sorted(values, key=lambda v: json.dumps(v, sort_keys=True)), sort_keys=True, ensure_ascii=False)


def validate_event_basis(text: str, context: dict, prior_context: dict | None = None, prior_text: str = '') -> None:
    """Reject invented normalized dates without requiring a time on any fact."""
    proposed = time_context(text, context['stated_at'])['events']
    available = context.get('events', []) + (prior_context or {}).get('events', [])
    for event in proposed:
        if event['expression'] in TOKEN.findall(prior_text):
            continue  # Retained relative wording still belongs to the old fact's clock.
        if event.get('value') is not None and not any(
            (event['precision'], event['value'], event.get('end_value')) ==
            (old['precision'], old.get('value'), old.get('end_value')) for old in available
        ):
            raise ValueError('memory_event_without_user_basis')


def validity(statement: str, stated_at: str) -> dict:
    """Only explicit applicability language creates a usable-window boundary."""
    clauses = re.split(r'[，。；;,\n]', statement)
    result = {}
    said = datetime.fromisoformat(stated_at.replace('Z', '+00:00')).astimezone(TZ)
    for clause in clauses:
        if not VALIDITY.search(clause):
            continue
        matches = list(TOKEN.finditer(clause))
        if not matches:
            continue
        for match in matches:
            precision, value, end = _resolve(match.group(), said)
            if not value:
                raise ValueError('memory_validity_needs_clarification')
            start_only = bool(re.search(r'(?:从|自).*(?:起|开始).*(?:有效|适用)', clause)) and len(matches) == 1
            before = bool(re.match(r'\s*(?:之前|以前|前)', clause[match.end():])) and match.group() != '月底'
            if precision == 'month':
                y, m = map(int, value.split('-'))
                boundary = datetime(y, m, 1, tzinfo=TZ)
                if not start_only and not before:
                    y, m0 = divmod(y * 12 + m, 12)
                    boundary = datetime(y, m0 + 1, 1, tzinfo=TZ)
            elif precision == 'week':
                y, w = value.split('-W')
                boundary = datetime.fromisocalendar(int(y), int(w), 1).replace(tzinfo=TZ)
                if not start_only:
                    boundary += timedelta(days=7)
            elif precision in {'day', 'range'}:
                boundary = datetime.fromisoformat(end or value).replace(tzinfo=TZ)
                if not start_only and not before and precision == 'day':
                    boundary += timedelta(days=1)
            else:
                raise ValueError('memory_validity_needs_clarification')
            result['valid_from' if start_only else 'expires_at'] = boundary.astimezone(timezone.utc).isoformat(timespec='seconds')
    if result:
        result.update(validity_note=f'原话：{statement[:180]}；按陈述时间 {said.isoformat(timespec="seconds")} 解释', validity_timezone='Asia/Shanghai')
    return result


def checked_validity(statement: str, stated_at: str, fields: dict) -> dict:
    derived = validity(statement, stated_at)
    for key in ('valid_from', 'expires_at'):
        if key in fields and fields[key] is not None:
            value = datetime.fromisoformat(fields[key].replace('Z', '+00:00'))
            if value.tzinfo is None:
                raise ValueError('memory_time_requires_timezone')
            canonical = value.astimezone(timezone.utc).isoformat(timespec='seconds')
            if canonical != derived.get(key):
                raise ValueError('memory_validity_without_user_basis')
        if key in fields and fields[key] is None:
            derived[key] = None
    result = {key: derived.get(key) for key in ('valid_from', 'expires_at') if key in fields}
    if any(value is not None for value in result.values()):
        result.update({key: value for key, value in derived.items() if key in ('validity_note', 'validity_timezone')})
    return result


def time_summary(context: dict) -> str:
    return '；'.join(f"{e.get('expression', '')} → {e.get('value') or '具体时间未定'}"
                    + (f" 至 {e['end_value']}" if e.get('end_value') else '') for e in context.get('events', []))


def has_personal_candidate(messages: list[dict]) -> bool:
    """Exclude only complete, obvious non-facts; no first-person prerequisite."""
    def excluded(text: str) -> bool:
        if re.fullmatch(r'\s*(?:你好|您好|嗨|谢谢|感谢|再见|hello|hi|thanks|(?:请)?(?:这次|本次)?(?:回答|回复)?(?:简短一点|短一点|用中文|用英文|分点回答|只列要点))[!！。，,.~～\s]*', text, re.I):
            return True
        definition_request = re.fullmatch(r'\s*(?:什么是|(?:请)?(?:解释|介绍)(?:一下)?)[^，。；;\n]+[?？]?\s*', text)
        return bool(definition_request and not TOKEN.search(text) and not re.search(r'决定|打算|喜欢|正在|计划|考虑|采用|不使用', text))
    return any(not excluded(str(m['content'])) for m in messages)
