import tempfile
import unittest
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from google.genai import errors as genai_errors
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError

from ml import retail_ml
from schemas.auth import UserLogin, UserRegister
from services import ai_agent_service, analytics_service, auth_service
from services import gemini_service
from services import ml_integration_service


class ConfirmedOrderFilterTests(unittest.TestCase):
    def assert_confirmed_filter(self, statement):
        sql = str(
            statement.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )
        self.assertIn("status =", sql)
        self.assertIn("'confirmed'", sql)
        self.assertNotIn("status !=", sql)

    def make_db(self):
        db = Mock()
        db.scalar.return_value = SimpleNamespace(id=uuid.uuid4())
        db.execute.return_value.all.return_value = []
        return db

    def test_analytics_queries_only_include_confirmed_orders(self):
        shop_id = uuid.uuid4()

        overview_db = self.make_db()
        overview_db.scalar.side_effect = [
            SimpleNamespace(id=shop_id),
            1,
        ]
        overview_db.execute.return_value.one.return_value = (
            1,
            Decimal("10.00"),
        )
        analytics_service.get_sales_overview(
            overview_db,
            SimpleNamespace(id=uuid.uuid4()),
            shop_id,
        )
        self.assert_confirmed_filter(
            overview_db.execute.call_args.args[0]
        )
        self.assert_confirmed_filter(
            overview_db.scalar.call_args_list[1].args[0]
        )

        for method in (
            analytics_service.get_daily_sales,
            analytics_service.get_monthly_sales,
            analytics_service.get_top_selling_products,
        ):
            with self.subTest(method=method.__name__):
                db = self.make_db()
                method(db, SimpleNamespace(id=uuid.uuid4()), shop_id)
                self.assert_confirmed_filter(db.execute.call_args.args[0])

    def test_ml_history_queries_only_include_confirmed_orders(self):
        shop_id = uuid.uuid4()
        product_id = uuid.uuid4()

        history_db = self.make_db()
        ml_integration_service.get_product_daily_history(
            history_db,
            shop_id,
            product_id,
            datetime.now(),
        )
        self.assert_confirmed_filter(
            history_db.execute.call_args.args[0]
        )

        forecast_db = self.make_db()
        ml_integration_service.get_sales_forecast(
            forecast_db,
            SimpleNamespace(id=uuid.uuid4()),
            shop_id,
        )
        self.assert_confirmed_filter(
            forecast_db.execute.call_args.args[0]
        )

        anomaly_db = self.make_db()
        anomaly_db.execute.return_value.one.return_value = SimpleNamespace(
            units=0,
            revenue=Decimal("0.00"),
            orders=0,
        )
        ml_integration_service.get_sales_anomaly_report(
            anomaly_db,
            SimpleNamespace(id=uuid.uuid4()),
            shop_id,
        )
        self.assert_confirmed_filter(
            anomaly_db.execute.call_args.args[0]
        )

    def test_legacy_recommendation_history_only_includes_confirmed_orders(self):
        db = self.make_db()
        ai_agent_service.run_demand_forecasting_agent(
            db,
            SimpleNamespace(id=uuid.uuid4()),
            uuid.uuid4(),
        )
        self.assert_confirmed_filter(db.execute.call_args.args[0])


class ModelCacheTests(unittest.TestCase):
    def setUp(self):
        retail_ml.load_models.cache_clear()

    def tearDown(self):
        retail_ml.load_models.cache_clear()

    @staticmethod
    def valid_bundle():
        class Model:
            def __init__(self, feature_count):
                self.n_features_in_ = feature_count

            classes_ = [0, 1]

            def predict(self, data):
                return [0] * len(data)

            def predict_proba(self, data):
                return [[1, 0]] * len(data)

            def decision_function(self, data):
                return [0] * len(data)

        return {
            "schema_version": retail_ml.MODEL_SCHEMA_VERSION,
            "demand_model": Model(len(retail_ml.DEMAND_FEATURES)),
            "stockout_model": Model(len(retail_ml.STOCKOUT_FEATURES)),
            "sales_model": Model(len(retail_ml.SALES_FEATURES)),
            "anomaly_model": Model(len(retail_ml.ANOMALY_FEATURES)),
            "demand_features": retail_ml.DEMAND_FEATURES,
            "stockout_features": retail_ml.STOCKOUT_FEATURES,
            "sales_features": retail_ml.SALES_FEATURES,
            "anomaly_features": retail_ml.ANOMALY_FEATURES,
            "feature_metadata": retail_ml.FEATURE_METADATA,
            "model_version": retail_ml.MODEL_VERSION,
            "training_source": "synthetic_retail_data",
            "validation_status": "experimental_synthetic",
        }

    def test_model_bundle_is_loaded_once_and_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            model_path = Path(directory) / "bundle.joblib"
            model_path.touch()
            bundle = self.valid_bundle()
            with (
                patch.object(retail_ml, "MODEL_PATH", model_path),
                patch.object(retail_ml.joblib, "load", return_value=bundle) as load,
            ):
                first = retail_ml.load_models()
                second = retail_ml.load_models()

            self.assertIs(first, second)
            load.assert_called_once_with(model_path)

    def test_missing_model_artifact_has_a_clear_error(self):
        with tempfile.TemporaryDirectory() as directory:
            missing_path = Path(directory) / "missing.joblib"
            with patch.object(retail_ml, "MODEL_PATH", missing_path):
                with self.assertRaises(retail_ml.ModelArtifactError):
                    retail_ml.load_models()

    def test_unreadable_model_artifact_has_a_clear_error(self):
        with tempfile.TemporaryDirectory() as directory:
            model_path = Path(directory) / "bundle.joblib"
            model_path.touch()
            with (
                patch.object(retail_ml, "MODEL_PATH", model_path),
                patch.object(retail_ml.joblib, "load", side_effect=EOFError),
            ):
                with self.assertRaisesRegex(
                    retail_ml.ModelArtifactError,
                    "unreadable or incompatible",
                ):
                    retail_ml.load_models()

    def test_incomplete_model_bundle_has_a_clear_error(self):
        with tempfile.TemporaryDirectory() as directory:
            model_path = Path(directory) / "bundle.joblib"
            model_path.touch()
            with (
                patch.object(retail_ml, "MODEL_PATH", model_path),
                patch.object(retail_ml.joblib, "load", return_value={}),
            ):
                with self.assertRaisesRegex(
                    retail_ml.ModelArtifactError,
                    "incomplete",
                ):
                    retail_ml.load_models()

    def test_feature_mismatch_in_model_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            model_path = Path(directory) / "bundle.joblib"
            model_path.touch()
            bundle = self.valid_bundle()
            bundle["sales_model"].n_features_in_ -= 1
            with (
                patch.object(retail_ml, "MODEL_PATH", model_path),
                patch.object(retail_ml.joblib, "load", return_value=bundle),
            ):
                with self.assertRaisesRegex(
                    retail_ml.ModelArtifactError,
                    "stale or incompatible",
                ):
                    retail_ml.load_models()


class EmailNormalizationTests(unittest.TestCase):
    def test_registration_and_login_emails_are_normalized(self):
        registration = UserRegister(
            full_name="Test Merchant",
            email="  Merchant@Example.com ",
            password="long-enough-password",
        )
        login = UserLogin(
            email="  MERCHANT@example.com ",
            password="long-enough-password",
        )

        self.assertEqual(registration.email, "merchant@example.com")
        self.assertEqual(login.email, "merchant@example.com")

    def test_registration_checks_existing_email_case_insensitively(self):
        db = Mock()
        db.scalar.return_value = SimpleNamespace()
        user_data = UserRegister(
            full_name="Test Merchant",
            email="Merchant@Example.com",
            password="long-enough-password",
        )

        with self.assertRaisesRegex(ValueError, "already exists"):
            auth_service.register_user(db, user_data)

        self.assertEqual(db.scalar.call_count, 1)
        db.add.assert_not_called()

    def test_registration_rolls_back_on_database_uniqueness_conflict(self):
        db = Mock()
        db.scalar.return_value = None
        db.commit.side_effect = IntegrityError(
            "INSERT",
            {},
            Exception("unique violation"),
        )
        user_data = UserRegister(
            full_name="Test Merchant",
            email="Merchant@Example.com",
            password="long-enough-password",
        )

        with patch.object(auth_service, "hash_password", return_value="hash"):
            with self.assertRaisesRegex(ValueError, "already exists"):
                auth_service.register_user(db, user_data)

        db.rollback.assert_called_once()


class GeminiErrorHandlingTests(unittest.IsolatedAsyncioTestCase):
    async def call_gemini_with(self, response_or_error):
        generate_content = AsyncMock()
        if isinstance(response_or_error, BaseException):
            generate_content.side_effect = response_or_error
        else:
            generate_content.return_value = response_or_error

        client = SimpleNamespace(
            aio=SimpleNamespace(
                models=SimpleNamespace(generate_content=generate_content)
            )
        )
        with (
            patch.object(gemini_service.settings, "GEMINI_API_KEY", "test-key"),
            patch.object(gemini_service, "get_gemini_client", return_value=client),
        ):
            return await gemini_service.ask_gemini(
                "How are sales?",
                {"orders": [{"status": "confirmed"}]},
                [],
            )

    async def test_empty_response_has_a_safe_specific_error(self):
        with self.assertRaises(gemini_service.GeminiEmptyResponseError):
            await self.call_gemini_with(SimpleNamespace(text="  "))

    async def test_quota_error_is_reported_without_provider_details(self):
        provider_error = genai_errors.ClientError(
            429,
            {
                "status": "RESOURCE_EXHAUSTED",
                "message": "sensitive detail",
            },
        )
        with self.assertRaises(gemini_service.GeminiQuotaError) as raised:
            await self.call_gemini_with(provider_error)

        self.assertNotIn("sensitive detail", str(raised.exception))

    async def test_timeout_has_a_safe_specific_error(self):
        with self.assertRaises(gemini_service.GeminiTimeoutError):
            await self.call_gemini_with(TimeoutError())


if __name__ == "__main__":
    unittest.main()
