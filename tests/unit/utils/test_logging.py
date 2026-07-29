import json
import logging

from utils.helpers import JsonFormatter, RequestIdFilter, setup_logging
from utils.request_context import request_id_var


def test_setup_logging_returns_named_logger():
    assert setup_logging("x.y").name == "x.y"


def test_json_formatter_includes_request_id():
    record = logging.LogRecord("mod", logging.INFO, __file__, 1, "hello %s", ("world",), None)
    RequestIdFilter().filter(record)
    payload = json.loads(JsonFormatter().format(record))
    assert payload["message"] == "hello world"
    assert payload["request_id"] == "-"


def test_request_id_filter_reads_contextvar():
    token = request_id_var.set("req-123")
    try:
        record = logging.LogRecord("mod", logging.INFO, __file__, 1, "m", (), None)
        RequestIdFilter().filter(record)
        assert record.request_id == "req-123"
    finally:
        request_id_var.reset(token)


def test_setup_logging_configures_root_once():
    setup_logging("a")
    n = len(logging.getLogger().handlers)
    setup_logging("b")
    assert len(logging.getLogger().handlers) == n
