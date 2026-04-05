"""Tests for retry decorators."""

from unittest.mock import MagicMock

import httpx
import pytest

from freya_observability.retry import (
    retry_db,
    retry_external_http,
    retry_inference,
)


class TestRetryExternalHttp:
    def test_succeeds_on_first_try(self):
        fn = MagicMock(return_value="ok")
        wrapped = retry_external_http(fn)
        assert wrapped() == "ok"
        assert fn.call_count == 1

    def test_retries_on_transport_error_then_succeeds(self):
        fn = MagicMock(side_effect=[
            httpx.ConnectError("boom"),
            httpx.ConnectError("boom"),
            "ok",
        ])
        wrapped = retry_external_http(fn)
        assert wrapped() == "ok"
        assert fn.call_count == 3

    def test_exhausts_after_three_attempts(self):
        fn = MagicMock(side_effect=httpx.ConnectError("persistent"))
        wrapped = retry_external_http(fn)
        with pytest.raises(httpx.ConnectError):
            wrapped()
        assert fn.call_count == 3

    def test_does_not_retry_on_unrelated_exception(self):
        fn = MagicMock(side_effect=ValueError("not retryable"))
        wrapped = retry_external_http(fn)
        with pytest.raises(ValueError):
            wrapped()
        assert fn.call_count == 1


class TestRetryInference:
    def test_succeeds_on_first_try(self):
        fn = MagicMock(return_value="ok")
        wrapped = retry_inference(fn)
        assert wrapped() == "ok"
        assert fn.call_count == 1

    def test_retries_on_connect_error_once_then_succeeds(self):
        fn = MagicMock(side_effect=[httpx.ConnectError("boom"), "ok"])
        wrapped = retry_inference(fn)
        assert wrapped() == "ok"
        assert fn.call_count == 2

    def test_exhausts_after_two_attempts(self):
        fn = MagicMock(side_effect=httpx.ConnectError("persistent"))
        wrapped = retry_inference(fn)
        with pytest.raises(httpx.ConnectError):
            wrapped()
        assert fn.call_count == 2


class TestRetryDb:
    def test_retries_on_connection_error(self):
        fn = MagicMock(side_effect=[
            ConnectionError("reset"),
            ConnectionError("reset"),
            "ok",
        ])
        wrapped = retry_db(fn)
        assert wrapped() == "ok"
        assert fn.call_count == 3

    def test_exhausts_after_five_attempts(self):
        fn = MagicMock(side_effect=ConnectionError("persistent"))
        wrapped = retry_db(fn)
        with pytest.raises(ConnectionError):
            wrapped()
        assert fn.call_count == 5
