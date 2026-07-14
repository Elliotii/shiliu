import logging

from shiliu.logging_config import RedactingFilter, redact_text


def test_sensitive_values_are_redacted() -> None:
    text = "Authorization: Bearer sk-secret api_key=another SESSDATA=cookie bili_jct=csrf"
    redacted = redact_text(text)
    assert "sk-secret" not in redacted
    assert "another" not in redacted
    assert "cookie" not in redacted
    assert "csrf" not in redacted
    assert redacted.count("[REDACTED]") == 4


def test_logging_filter_redacts_message_arguments() -> None:
    record = logging.LogRecord("shiliu.test", logging.INFO, __file__, 1, "api_key=%s", ("secret",), None)
    assert RedactingFilter().filter(record) is True
    assert "secret" not in record.getMessage()

