"""Incremental Final JSON fields and minimum-trust checked, provisional blocks."""
from __future__ import annotations

import json
import time
from typing import Callable

from pydantic import ValidationError

from shiliu.ask.contracts import AnswerDraftBlock
from shiliu.ask.trust import apply_answer_trust


class AnswerJSONStream:
    """Decode only complete JSON values; never expose partial strings or raw JSON.

    The final provider parser remains authoritative. Unsupported/malformed prefixes
    simply cannot deliver early. Repeated top-level fields retract this attempt.
    """
    def __init__(self, receive: Callable, invalid: Callable):
        self.receive, self.invalid = receive, invalid
        self.buffer = ''
        self.position = 0
        self.phase = 'start'
        self.key = None
        self.keys: set[str] = set()
        self.index = 0
        self.decoder = json.JSONDecoder()

    def feed(self, content: str):
        if self.phase == 'disabled':
            return
        self.buffer += content
        if len(self.buffer) > 1_000_000:
            self.disable()
            return
        while self.position < len(self.buffer):
            if self.buffer[self.position].isspace():
                self.position += 1
                continue
            ch = self.buffer[self.position]
            if self.phase == 'start':
                if ch != '{':
                    self.disable()
                    return
                self.position += 1
                self.phase = 'key'
            elif self.phase == 'key':
                if ch == '}':
                    self.position += 1
                    self.phase = 'done'
                    continue
                value = self.decode()
                if value is None:
                    return
                key, end = value
                if not isinstance(key, str) or key in self.keys:
                    self.disable()
                    return
                self.key = key
                self.keys.add(key)
                self.position = end
                self.phase = 'colon'
            elif self.phase == 'colon':
                if ch != ':':
                    self.disable()
                    return
                self.position += 1
                self.phase = 'value'
            elif self.phase == 'value' and self.key == 'answer_blocks':
                if ch != '[':
                    self.disable()
                    return
                self.position += 1
                self.phase = 'block'
            elif self.phase in {'value', 'block'}:
                if self.phase == 'block' and ch == ']':
                    self.position += 1
                    self.phase = 'separator'
                    self.receive('answer_blocks_end', None, None)
                    continue
                value = self.decode()
                if value is None:
                    return
                parsed, end = value
                self.position = end
                if self.phase == 'block':
                    self.receive('answer_block', self.index, parsed)
                    self.index += 1
                    self.phase = 'block_separator'
                else:
                    self.receive(self.key, None, parsed)
                    self.phase = 'separator'
            elif self.phase in {'separator', 'block_separator'}:
                array = self.phase == 'block_separator'
                if ch == ',':
                    self.position += 1
                    self.phase = 'block' if array else 'key'
                elif ch == (']' if array else '}'):
                    self.position += 1
                    self.phase = 'separator' if array else 'done'
                    if array:
                        self.receive('answer_blocks_end', None, None)
                else:
                    self.disable()
                    return
            else:
                self.disable()
                return

    def decode(self):
        try:
            return self.decoder.raw_decode(self.buffer, self.position)
        except json.JSONDecodeError:
            return None

    def disable(self):
        self.phase = 'disabled'
        self.invalid()


class AnswerStreamDelivery:
    def __init__(self, *, context, run_id, validate_current, event_sink, clock=time.monotonic):
        self.context, self.run_id = context, run_id
        self.validate_current, self.event_sink, self.clock = validate_current, event_sink, clock
        self.started = clock()
        self.generation = 0
        self.metrics = {'started_at_ms': time.time() * 1000, 'first_block_ms': None,
                        'delivered_blocks': 0, 'resets': 0}
        self.emit('answer_generation_started', self.metrics.copy())
        self.new_parser()

    def emit(self, kind, payload):
        # Delivery faults must not regenerate the answer or consume Repair budget.
        try:
            self.event_sink(kind, {**payload, 'generation': self.generation})
            return True
        except Exception:
            self.metrics['delivery_error'] = True
            return False

    def new_parser(self):
        self.intro = self.outro = None
        self.array_complete = False
        self.has_blocks = False
        self.insufficient = False
        self.seen: set[tuple] = set()
        self.parser = AnswerJSONStream(self.receive, self.retract)

    def retract(self):
        self.has_blocks = False
        self.emit('answer_stream_reset', {})

    def reset(self):
        self.generation += 1
        self.metrics['resets'] += 1
        self.retract()
        self.new_parser()

    def feed(self, content):
        try:
            self.parser.feed(content)
        except Exception:
            # Early delivery is optional. It must never create a Provider retry.
            self.metrics['delivery_error'] = True
            self.parser.disable()

    def framing(self):
        return {'intro': self.intro, 'outro': self.outro if self.array_complete else None}

    def receive(self, field, index, value):
        if field == 'status' and value == 'insufficient':
            self.insufficient = True
            self.retract()
        elif field in {'intro', 'outro'} and (value is None or isinstance(value, str)):
            setattr(self, field, value.strip() or None if value is not None else None)
            if self.has_blocks:
                self.emit('answer_part', self.framing())
        elif field == 'answer_blocks_end':
            self.array_complete = True
            if self.has_blocks and self.outro:
                self.emit('answer_part', self.framing())
        elif field == 'answer_block' and not self.insufficient:
            try:
                block = AnswerDraftBlock.model_validate(value)
            except ValidationError:
                return
            refs = set(block.citation_ids)
            if not refs or not refs.issubset(self.context.citation_allowlist):
                return
            selected = tuple(s for s in self.context.spans if s.citation_id in refs)
            trusted = apply_answer_trust(run_id=self.run_id, answer_blocks=[block],
                citations=tuple(s.as_citation() for s in selected), spans=selected,
                status='complete', limitations=[], termination_reason='answer_ready',
                validate_current=self.validate_current)
            if not trusted.answer_blocks:
                return
            signature = (' '.join(block.text.casefold().split()).rstrip('。.!！?'), tuple(sorted(refs)))
            if signature in self.seen:
                return
            self.seen.add(signature)
            self.has_blocks = True
            elapsed = (self.clock() - self.started) * 1000
            delivered = self.emit('answer_part', {**self.framing(), 'index': index,
                'block': trusted.answer_blocks[0].model_dump(mode='json'),
                'citations': [c.model_dump(mode='json') for c in trusted.citations],
                'elapsed_ms': elapsed})
            if delivered:
                if self.metrics['first_block_ms'] is None:
                    self.metrics['first_block_ms'] = elapsed
                self.metrics['delivered_blocks'] += 1

    def finish(self):
        self.metrics.update(generation_ms=(self.clock() - self.started) * 1000,
                            completed_at_ms=time.time() * 1000)
        self.emit('answer_generation_finished', self.metrics.copy())
