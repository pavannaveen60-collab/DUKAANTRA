import asyncio
import logging
import unittest
import uuid
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException
from google.genai import errors as genai_errors

from api.routes import ai_chat
from services import gemini_service


class GeminiRetryTests(unittest.IsolatedAsyncioTestCase):
    def make_client(self, generate_content):
        return SimpleNamespace(
            aio=SimpleNamespace(
                models=SimpleNamespace(generate_content=generate_content)
            )
        )

    async def ask_with(self, generate_content, question="How are sales?", context=None):
        with (
            patch.object(gemini_service.settings, "GEMINI_API_KEY", "test-api-key"),
            patch.object(
                gemini_service,
                "get_gemini_client",
                return_value=self.make_client(generate_content),
            ),
        ):
            return await gemini_service.ask_gemini(
                question,
                context or {"shop": "test shop"},
                [],
            )

    async def test_transient_typed_5xx_retries_once(self):
        generate_content = AsyncMock(
            side_effect=[
                genai_errors.ServerError(
                    503,
                    {"status": "UNAVAILABLE", "message": "temporary"},
                ),
                SimpleNamespace(text="Sales are steady."),
            ]
        )

        with patch.object(gemini_service.asyncio, "sleep", new_callable=AsyncMock):
            answer = await self.ask_with(generate_content)

        self.assertEqual(answer, "Sales are steady.")
        self.assertEqual(generate_content.await_count, 2)

    async def test_provider_504_becomes_timeout_without_retry(self):
        generate_content = AsyncMock(
            side_effect=genai_errors.ServerError(
                504,
                {
                    "status": "DEADLINE_EXCEEDED",
                    "message": "sensitive provider response",
                },
            )
        )

        with self.assertRaises(gemini_service.GeminiTimeoutError) as raised:
            await self.ask_with(generate_content)

        generate_content.assert_awaited_once()
        self.assertNotIn("sensitive provider response", str(raised.exception))

    async def test_deadline_exceeded_status_is_timeout_even_if_code_differs(self):
        generate_content = AsyncMock(
            side_effect=genai_errors.ServerError(
                503,
                {"status": "DEADLINE_EXCEEDED"},
            )
        )

        with self.assertRaises(gemini_service.GeminiTimeoutError):
            await self.ask_with(generate_content)

        generate_content.assert_awaited_once()

    async def test_exhausted_transient_5xx_fails_after_two_attempts(self):
        error = genai_errors.ServerError(
            503,
            {"status": "UNAVAILABLE", "message": "provider details"},
        )
        generate_content = AsyncMock(side_effect=error)

        with (
            patch.object(gemini_service.asyncio, "sleep", new_callable=AsyncMock),
            self.assertRaises(gemini_service.GeminiServiceError),
        ):
            await self.ask_with(generate_content)

        self.assertEqual(generate_content.await_count, 2)

    async def test_non_transient_server_error_does_not_retry(self):
        generate_content = AsyncMock(
            side_effect=genai_errors.ServerError(
                501,
                {"status": "NOT_IMPLEMENTED"},
            )
        )

        with self.assertRaises(gemini_service.GeminiServiceError):
            await self.ask_with(generate_content)

        generate_content.assert_awaited_once()

    async def test_permanent_4xx_does_not_retry(self):
        generate_content = AsyncMock(
            side_effect=genai_errors.ClientError(
                400,
                {"status": "INVALID_ARGUMENT", "message": "private detail"},
            )
        )

        with self.assertRaises(gemini_service.GeminiServiceError):
            await self.ask_with(generate_content)

        generate_content.assert_awaited_once()

    async def test_quota_and_rate_limit_are_distinct_and_not_retried(self):
        generate_content = AsyncMock(
            side_effect=genai_errors.ClientError(
                429,
                {"status": "RESOURCE_EXHAUSTED"},
            )
        )

        with self.assertRaises(gemini_service.GeminiQuotaError):
            await self.ask_with(generate_content)

        generate_content.assert_awaited_once()

    async def test_logs_only_sanitized_provider_diagnostics(self):
        provider_error = genai_errors.ServerError(
            503,
            {
                "status": "UNAVAILABLE",
                "message": "provider-response-secret",
            },
            response=SimpleNamespace(
                headers={"x-goog-request-id": "request-123"}
            ),
        )
        generate_content = AsyncMock(
            side_effect=[
                provider_error,
                SimpleNamespace(text="Available."),
            ]
        )

        with (
            patch.object(gemini_service.asyncio, "sleep", new_callable=AsyncMock),
            self.assertLogs("dukaantra.ai", logging.WARNING) as captured,
        ):
            await self.ask_with(
                generate_content,
                question="merchant-prompt-secret",
                context={"customer": "merchant-context-secret"},
            )

        log_output = "\n".join(captured.output)
        self.assertIn("status=UNAVAILABLE", log_output)
        self.assertIn("code=503", log_output)
        self.assertIn("request_id=request-123", log_output)
        self.assertNotIn("provider-response-secret", log_output)
        self.assertNotIn("merchant-prompt-secret", log_output)
        self.assertNotIn("merchant-context-secret", log_output)
        self.assertNotIn("test-api-key", log_output)

    async def test_attempt_timeout_is_reported_safely(self):
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def delayed_generation(**kwargs):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        generate_content = AsyncMock(side_effect=delayed_generation)
        with (
            patch.object(gemini_service, "REQUEST_TIMEOUT", 0.01),
            self.assertRaises(gemini_service.GeminiTimeoutError),
        ):
            await self.ask_with(generate_content)

        self.assertTrue(started.is_set())
        self.assertTrue(cancelled.is_set())
        generate_content.assert_awaited_once()

    async def test_total_deadline_cancels_the_provider_call(self):
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def delayed_generation(**kwargs):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        generate_content = AsyncMock(side_effect=delayed_generation)
        with (
            patch.object(gemini_service, "REQUEST_TIMEOUT", 1),
            patch.object(gemini_service, "REQUEST_DEADLINE", 0.01),
            self.assertRaises(gemini_service.GeminiTimeoutError),
        ):
            await self.ask_with(generate_content)

        self.assertTrue(started.is_set())
        self.assertTrue(cancelled.is_set())
        generate_content.assert_awaited_once()

    async def test_cancellation_propagates_and_cancels_provider_call(self):
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def delayed_generation(**kwargs):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        generate_content = AsyncMock(side_effect=delayed_generation)
        with (
            patch.object(gemini_service.settings, "GEMINI_API_KEY", "test-api-key"),
            patch.object(
                gemini_service,
                "get_gemini_client",
                return_value=self.make_client(generate_content),
            ),
        ):
            task = asyncio.create_task(
                gemini_service.ask_gemini("Question", {}, [])
            )
            await started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

        self.assertTrue(cancelled.is_set())

    async def test_sdk_retry_is_disabled_in_client_configuration(self):
        client = Mock()
        with (
            patch.object(gemini_service.settings, "GEMINI_API_KEY", "test-api-key"),
            patch.object(gemini_service, "_client", None),
            patch.object(gemini_service, "_client_api_key", None),
            patch.object(gemini_service.genai, "Client", return_value=client) as factory,
        ):
            gemini_service.get_gemini_client()

        options = factory.call_args.kwargs["http_options"]
        self.assertEqual(options.retry_options.attempts, 1)
        self.assertEqual(
            options.timeout,
            gemini_service.REQUEST_TIMEOUT * 1000,
        )


class GeminiChatRouteTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.shop_id = uuid.uuid4()
        self.owner_id = uuid.uuid4()
        self.shop = SimpleNamespace(
            id=self.shop_id,
            owner_id=self.owner_id,
            shop_name="Test Shop",
            business_type="Retail",
            city="Pune",
            state="MH",
        )
        self.user = SimpleNamespace(id=self.owner_id)
        self.product = SimpleNamespace(
            name="Tea",
            category="Grocery",
            price=Decimal("10.00"),
            sku="TEA-1",
            is_active=True,
        )
        self.inventory = SimpleNamespace(
            quantity=12,
            low_stock_threshold=3,
        )
        self.order = SimpleNamespace(
            order_number="ORD-1",
            status="confirmed",
            total_amount=Decimal("20.00"),
            created_at=datetime(2026, 1, 2),
        )
        self.db = Mock()
        self.db.scalar.return_value = self.shop
        self.db.execute.return_value.all.return_value = [
            (self.product, self.inventory)
        ]
        self.db.scalars.return_value.all.return_value = [self.order]

    async def call_route(self):
        with patch.object(ai_chat.settings, "GEMINI_API_KEY", "test-api-key"):
            return await ai_chat.chat_with_dukaantra(
                self.shop_id,
                ai_chat.ChatRequest(message="How is my business doing?"),
                self.db,
                self.user,
            )

    async def test_chat_forwards_only_authorized_shop_context(self):
        with (
            patch.object(ai_chat.settings, "GEMINI_API_KEY", "test-api-key"),
            patch.object(
                ai_chat,
                "ask_gemini",
                new_callable=AsyncMock,
                return_value="Your shop has one recent confirmed order.",
            ) as ask_gemini,
        ):
            result = await self.call_route()

        self.assertTrue(result["success"])
        self.assertEqual(ask_gemini.await_count, 1)
        question, context, history = ask_gemini.await_args.args
        self.assertEqual(question, "How is my business doing?")
        self.assertEqual(history, [])
        self.assertEqual(context["shop"]["name"], "Test Shop")
        self.assertEqual(context["products"][0]["name"], "Tea")
        self.assertEqual(context["recent_orders"][0]["order_number"], "ORD-1")

        compiled_query = str(self.db.scalar.call_args.args[0])
        self.assertIn("owner_id", compiled_query)

    async def test_shop_not_owned_returns_404_without_calling_gemini(self):
        self.db.scalar.return_value = None
        with (
            patch.object(ai_chat.settings, "GEMINI_API_KEY", "test-api-key"),
            patch.object(ai_chat, "ask_gemini", new_callable=AsyncMock) as ask_gemini,
            self.assertRaises(HTTPException) as raised,
        ):
            await self.call_route()

        self.assertEqual(raised.exception.status_code, 404)
        ask_gemini.assert_not_awaited()

    async def test_route_maps_provider_timeout_to_http_504(self):
        with (
            patch.object(ai_chat.settings, "GEMINI_API_KEY", "test-api-key"),
            patch.object(
                ai_chat,
                "ask_gemini",
                new_callable=AsyncMock,
                side_effect=gemini_service.GeminiTimeoutError(
                    "Gemini took too long to respond. Please try again."
                ),
            ),
            self.assertRaises(HTTPException) as raised,
        ):
            await self.call_route()

        self.assertEqual(raised.exception.status_code, 504)
