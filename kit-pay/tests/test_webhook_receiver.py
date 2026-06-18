"""Tests for kit_pay.webhook_receiver using fakeredis."""

from __future__ import annotations

import hashlib
import hmac
import json

import fakeredis
import pytest
from kit_pay.webhook_receiver import ProcessStatus, WebhookEvent, WebhookReceiver


@pytest.fixture
def redis():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def receiver(redis):
    return WebhookReceiver(redis)


class TestWebhookVerification:
    def test_verify_valid_signature(self, receiver):
        payload = b'{"type": "invoice.paid"}'
        secret = "whsec_test123"
        signature = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        assert receiver.verify(payload, signature, secret) is True

    def test_verify_invalid_signature(self, receiver):
        payload = b'{"type": "invoice.paid"}'
        assert receiver.verify(payload, "bad_signature", "secret") is False


class TestWebhookParsing:
    def test_parse_stripe_event(self, receiver):
        payload = json.dumps({
            "id": "evt_123",
            "type": "invoice.paid",
            "created": 1700000000,
            "data": {"object": {"amount": 1000}},
        }).encode()

        event = receiver.parse(payload, provider="stripe")
        assert event.id == "evt_123"
        assert event.type == "invoice.paid"
        assert event.provider == "stripe"
        assert event.timestamp == 1700000000.0

    def test_parse_paddle_event(self, receiver):
        payload = json.dumps({
            "event_id": "ntf_456",
            "event_type": "subscription.created",
            "occurred_at": 1700000001,
            "data": {},
        }).encode()

        event = receiver.parse(payload, provider="paddle")
        assert event.id == "ntf_456"
        assert event.type == "subscription.created"
        assert event.provider == "paddle"


class TestWebhookProcessing:
    def test_register_and_dispatch_handler(self, receiver):
        results = []

        def handler(event: WebhookEvent):
            results.append(event.type)
            return "handled"

        receiver.register_handler("invoice.paid", handler)

        event = WebhookEvent(
            id="evt_001",
            type="invoice.paid",
            provider="stripe",
            data={},
            timestamp=1700000000.0,
            raw=b"{}",
        )

        result = receiver.process(event)
        assert result.status == ProcessStatus.SUCCESS
        assert results == ["invoice.paid"]
        assert result.handler_results == ["handled"]

    def test_deduplicates_events(self, receiver):
        call_count = 0

        def handler(event):
            nonlocal call_count
            call_count += 1

        receiver.register_handler("test.event", handler)

        event = WebhookEvent(
            id="evt_dup",
            type="test.event",
            provider="stripe",
            data={},
            timestamp=1700000000.0,
            raw=b"{}",
        )

        receiver.process(event)
        result2 = receiver.process(event)

        assert call_count == 1
        assert result2.status == ProcessStatus.SKIPPED

    def test_unhandled_event_type_succeeds(self, receiver):
        event = WebhookEvent(
            id="evt_no_handler",
            type="unknown.event",
            provider="stripe",
            data={},
            timestamp=1700000000.0,
            raw=b"{}",
        )
        result = receiver.process(event)
        assert result.status == ProcessStatus.SUCCESS

    def test_handler_exception_returns_failed(self, receiver):
        def bad_handler(event):
            raise RuntimeError("handler crashed")

        receiver.register_handler("crash.event", bad_handler)

        event = WebhookEvent(
            id="evt_crash",
            type="crash.event",
            provider="stripe",
            data={},
            timestamp=1700000000.0,
            raw=b"{}",
        )
        result = receiver.process(event)
        assert result.status == ProcessStatus.FAILED
        assert "handler crashed" in result.error
