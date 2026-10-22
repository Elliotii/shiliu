"""Explicit C1 contract for legacy offline Runtime scripts; never a product fallback."""
from dataclasses import replace

from shiliu.assistant.provider import OpenAICompatibleAssistantProvider


class OfflineRequestProvider:
    def __init__(self, script):
        self.script = script
        self.contract = OpenAICompatibleAssistantProvider(
            base_url='https://api.deepseek.com/v1', api_key='synthetic', model='deepseek-v4-flash')
        if hasattr(script, 'stream_turn'):
            self.stream_turn = script.stream_turn

    def prepare_request(self, **kwargs):
        return self.contract.prepare_request(**kwargs)

    def budget_request(self, *args, **kwargs):
        return self.contract.budget_request(*args, **kwargs)

    def prepare_compaction(self, *, messages, remaining_tokens, input_limit_tokens=None):
        return self.contract.prepare_compaction(messages=messages, remaining_tokens=remaining_tokens,
                                                input_limit_tokens=input_limit_tokens)

    def send_prepared(self, request, *, on_text=None, timeout_seconds=None):
        assert request.purpose == 'turn', 'this control fixture does not script summaries'
        body = request.body
        kwargs = dict(messages=body['messages'], tools=body['tools'], max_tokens=body['max_tokens'])
        turn = (self.script.stream_turn(**kwargs, on_text=on_text)
                if body.get('stream') else self.script.turn(**kwargs))
        # These pre-C1 fixtures return complete synthetic responses without wire metadata.
        if turn.finish_reason is None:
            turn = replace(turn, finish_reason='tool_calls' if turn.tool_calls else 'stop')
        return turn


def offline_provider(script):
    """Explicitly adapt legacy scripts; keep already declared request providers intact."""
    return script if hasattr(script, 'send_prepared') and hasattr(script, 'prepare_request') else OfflineRequestProvider(script)
