import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from types import SimpleNamespace

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from api.routes.orders import create_new_order
from app import app
from core.dependencies import get_current_user
from database import get_db
from models.inventory import Inventory
from models.inventory_movement import InventoryMovement
from models.order import Order
from models.order_idempotency import OrderIdempotency
from models.order_item import OrderItem
from models.product import Product
from models.shop import Shop
from models.user import User
from schemas.order import OrderCreate


DATABASE_URL = os.getenv("DUKAANTRA_TEST_DATABASE_URL")
DATABASE_NAME = "dukaantra_idempotency_disposable"
DISPOSABLE_SOCKET_PREFIX = "/tmp/dukaantra-idempotency-pg-"


class ConcurrentOrderSession(Session):
    pass


@event.listens_for(ConcurrentOrderSession, "before_flush")
def synchronize_idempotency_inserts(session, flush_context, instances):
    barrier = session.info.get("idempotency_insert_barrier")
    if barrier is None or not any(
        isinstance(instance, OrderIdempotency) for instance in session.new
    ):
        return

    session.info["idempotency_insert_barrier"] = None
    barrier.wait(timeout=20)


@unittest.skipUnless(
    DATABASE_URL,
    "Set DUKAANTRA_TEST_DATABASE_URL to the disposable PostgreSQL test database.",
)
class PostgreSQLOrderIdempotencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parsed_url = make_url(DATABASE_URL)
        socket_path = parsed_url.query.get("host") or parsed_url.host
        if (
            parsed_url.database != DATABASE_NAME
            or not isinstance(socket_path, str)
            or not socket_path.startswith(DISPOSABLE_SOCKET_PREFIX)
        ):
            raise RuntimeError(
                "Refusing to run destructive integration tests: the database "
                "must be the named disposable DUKAANTRA database on the "
                "isolated local PostgreSQL socket."
            )

        cls.engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        with cls.engine.connect() as connection:
            cls.default_isolation_level = connection.scalar(
                text("SHOW transaction_isolation")
            )
            revision = connection.scalar(
                text("SELECT version_num FROM alembic_version")
            )
            if revision != "202611110003":
                raise RuntimeError(
                    "The disposable test database must be migrated to head."
                )

        cls.sessions = sessionmaker(
            bind=cls.engine,
            class_=ConcurrentOrderSession,
            autoflush=False,
            expire_on_commit=False,
        )

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "engine"):
            cls.engine.dispose()

    def setUp(self):
        self.session_factory = self.sessions
        with self.engine.begin() as connection:
            connection.execute(text("TRUNCATE TABLE users CASCADE"))

        with self.sessions() as session:
            owner = User(
                full_name="Idempotency Test Owner",
                email="owner@example.test",
                password_hash="test-only",
            )
            other_owner = User(
                full_name="Second Test Owner",
                email="other@example.test",
                password_hash="test-only",
            )
            session.add_all([owner, other_owner])
            session.flush()

            self.owner_id = owner.id
            self.other_owner_id = other_owner.id
            self.shop_ids = []
            self.product_ids = []
            for shop_owner, shop_name in (
                (owner, "Primary Shop"),
                (owner, "Second Shop"),
                (other_owner, "Other Owner Shop"),
            ):
                shop = Shop(
                    owner_id=shop_owner.id,
                    shop_name=shop_name,
                    business_type="Retail",
                )
                session.add(shop)
                session.flush()
                product = Product(
                    shop_id=shop.id,
                    name=f"Product {shop_name}",
                    price=Decimal("2.50"),
                    is_active=True,
                )
                session.add(product)
                session.flush()
                session.add(
                    Inventory(
                        shop_id=shop.id,
                        product_id=product.id,
                        quantity=100,
                        low_stock_threshold=5,
                    )
                )
                self.shop_ids.append(shop.id)
                self.product_ids.append(product.id)
            session.commit()

        def database_override():
            with self.session_factory() as session:
                session.info["idempotency_insert_barrier"] = getattr(
                    self,
                    "request_barrier",
                    None,
                )
                yield session

        app.dependency_overrides[get_db] = database_override
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id=self.owner_id
        )
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)

    def _orders(self, session, shop_id):
        return session.scalar(
            select(func.count()).select_from(Order).where(
                Order.shop_id == shop_id
            )
        )

    def _idempotency_records(self, session, shop_id):
        return session.scalar(
            select(func.count())
            .select_from(OrderIdempotency)
            .where(OrderIdempotency.shop_id == shop_id)
        )

    def _inventory_quantity(self, session, shop_id, product_id):
        return session.scalar(
            select(Inventory.quantity).where(
                Inventory.shop_id == shop_id,
                Inventory.product_id == product_id,
            )
        )

    def _invoke_concurrently(
        self,
        shop_id,
        product_id,
        key,
        quantities,
        *,
        isolation_level=None,
    ):
        barrier = threading.Barrier(2)
        conflict_sqlstates = []
        conflict_lock = threading.Lock()
        engine = (
            self.engine.execution_options(isolation_level=isolation_level)
            if isolation_level
            else self.engine
        )
        sessions = sessionmaker(
            bind=engine,
            class_=ConcurrentOrderSession,
            autoflush=False,
            expire_on_commit=False,
        )
        self.session_factory = sessions
        self.request_barrier = barrier

        def capture_unique_conflict(exception_context):
            statement = exception_context.statement or ""
            original = exception_context.original_exception
            sqlstate = getattr(original, "sqlstate", None) or getattr(
                original,
                "pgcode",
                None,
            )
            if "order_idempotency" in statement and sqlstate in {
                "23505",
                "40001",
            }:
                with conflict_lock:
                    conflict_sqlstates.append(sqlstate)

        event.listen(engine, "handle_error", capture_unique_conflict)

        def submit(quantity):
            response = self.client.post(
                f"/api/v1/shops/{shop_id}/orders/",
                headers={"Idempotency-Key": key},
                json={
                    "customer_id": None,
                    "items": [
                        {"product_id": str(product_id), "quantity": quantity}
                    ],
                },
            )
            if response.status_code == 409:
                return HTTPException(
                    status_code=response.status_code,
                    detail=response.json()["detail"],
                )
            if response.status_code != 201:
                raise AssertionError(
                    f"Unexpected concurrent order response: "
                    f"{response.status_code}"
                )
            return response.json()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(submit, quantity)
                for quantity in quantities
            ]
            try:
                results = [future.result(timeout=40) for future in futures]
            finally:
                event.remove(engine, "handle_error", capture_unique_conflict)
                self.request_barrier = None
        return results, conflict_sqlstates

    def test_concurrent_identical_submissions_replay_one_order(self):
        shop_id, product_id = self.shop_ids[0], self.product_ids[0]
        results, conflict_sqlstates = self._invoke_concurrently(
            shop_id,
            product_id,
            "postgres-identical-request-key",
            [2, 2],
        )

        self.assertEqual(results[0]["id"], results[1]["id"])
        self.assertEqual(conflict_sqlstates, ["23505"])
        with self.sessions() as session:
            self.assertEqual(self._orders(session, shop_id), 1)
            self.assertEqual(self._idempotency_records(session, shop_id), 1)
            self.assertEqual(
                self._inventory_quantity(session, shop_id, product_id),
                98,
            )
            self.assertEqual(
                session.scalar(
                    select(func.count())
                    .select_from(InventoryMovement)
                    .where(InventoryMovement.shop_id == shop_id)
                ),
                1,
            )

    def test_concurrent_changed_payload_returns_one_conflict(self):
        shop_id, product_id = self.shop_ids[0], self.product_ids[0]
        results, conflict_sqlstates = self._invoke_concurrently(
            shop_id,
            product_id,
            "postgres-different-payload-key",
            [1, 3],
        )

        successful = [result for result in results if not isinstance(result, HTTPException)]
        conflicts = [result for result in results if isinstance(result, HTTPException)]
        self.assertEqual(len(successful), 1)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].status_code, 409)
        self.assertEqual(conflict_sqlstates, ["23505"])
        committed_quantity = successful[0]["items"][0]["quantity"]
        with self.sessions() as session:
            self.assertEqual(self._orders(session, shop_id), 1)
            self.assertEqual(self._idempotency_records(session, shop_id), 1)
            self.assertEqual(
                self._inventory_quantity(session, shop_id, product_id),
                100 - committed_quantity,
            )

    def test_repeatable_read_conflict_uses_a_fresh_snapshot(self):
        shop_id, product_id = self.shop_ids[0], self.product_ids[0]
        results, conflict_sqlstates = self._invoke_concurrently(
            shop_id,
            product_id,
            "postgres-repeatable-read-key",
            [2, 2],
            isolation_level="REPEATABLE READ",
        )

        self.assertEqual(results[0]["id"], results[1]["id"])
        self.assertEqual(conflict_sqlstates, ["23505"])
        with self.sessions() as session:
            self.assertEqual(self._orders(session, shop_id), 1)
            self.assertEqual(self._idempotency_records(session, shop_id), 1)
            self.assertEqual(
                self._inventory_quantity(session, shop_id, product_id),
                98,
            )

    def test_serializable_conflict_retries_serialization_failure(self):
        shop_id, product_id = self.shop_ids[0], self.product_ids[0]
        results, _ = self._invoke_concurrently(
            shop_id,
            product_id,
            "postgres-serializable-key",
            [2, 2],
            isolation_level="SERIALIZABLE",
        )

        self.assertEqual(results[0]["id"], results[1]["id"])
        with self.sessions() as session:
            self.assertEqual(self._orders(session, shop_id), 1)
            self.assertEqual(self._idempotency_records(session, shop_id), 1)
            self.assertEqual(
                self._inventory_quantity(session, shop_id, product_id),
                98,
            )

    def test_different_keys_make_distinct_orders_and_deductions(self):
        shop_id, product_id = self.shop_ids[0], self.product_ids[0]
        for key in ("postgres-new-order-key-1", "postgres-new-order-key-2"):
            with self.sessions() as session:
                owner = session.get(User, self.owner_id)
                create_new_order(
                    shop_id,
                    OrderCreate(
                        items=[{"product_id": product_id, "quantity": 2}]
                    ),
                    key,
                    session,
                    owner,
                )

        with self.sessions() as session:
            self.assertEqual(self._orders(session, shop_id), 2)
            self.assertEqual(self._idempotency_records(session, shop_id), 2)
            self.assertEqual(
                self._inventory_quantity(session, shop_id, product_id),
                96,
            )

    def test_failed_order_rolls_back_reservation_and_can_be_retried(self):
        shop_id, product_id = self.shop_ids[0], self.product_ids[0]
        key = "postgres-rollback-key"
        with self.sessions() as session:
            owner = session.get(User, self.owner_id)
            with self.assertRaises(HTTPException):
                create_new_order(
                    shop_id,
                    OrderCreate(
                        items=[
                            {"product_id": product_id, "quantity": 101}
                        ]
                    ),
                    key,
                    session,
                    owner,
                )

        with self.sessions() as session:
            self.assertEqual(self._orders(session, shop_id), 0)
            self.assertEqual(self._idempotency_records(session, shop_id), 0)
            inventory = session.scalar(
                select(Inventory).where(
                    Inventory.shop_id == shop_id,
                    Inventory.product_id == product_id,
                )
            )
            inventory.quantity = 101
            session.commit()

        with self.sessions() as session:
            owner = session.get(User, self.owner_id)
            result = create_new_order(
                shop_id,
                OrderCreate(
                    items=[{"product_id": product_id, "quantity": 101}]
                ),
                key,
                session,
                owner,
            )
            self.assertIsNotNone(result["id"])

        with self.sessions() as session:
            self.assertEqual(self._orders(session, shop_id), 1)
            self.assertEqual(self._idempotency_records(session, shop_id), 1)
            self.assertEqual(
                self._inventory_quantity(session, shop_id, product_id),
                0,
            )

    def test_same_key_isolated_between_authorized_shops_and_users(self):
        key = "postgres-cross-scope-key"
        scopes = (
            (self.owner_id, self.shop_ids[0], self.product_ids[0]),
            (self.owner_id, self.shop_ids[1], self.product_ids[1]),
            (self.other_owner_id, self.shop_ids[2], self.product_ids[2]),
        )

        results = []
        for user_id, shop_id, product_id in scopes:
            with self.sessions() as session:
                owner = session.get(User, user_id)
                results.append(
                    create_new_order(
                        shop_id,
                        OrderCreate(
                            items=[
                                {"product_id": product_id, "quantity": 1}
                            ]
                        ),
                        key,
                        session,
                        owner,
                    )
                )

        self.assertEqual(len({result["id"] for result in results}), 3)
        with self.sessions() as session:
            for _, shop_id, _ in scopes:
                self.assertEqual(self._orders(session, shop_id), 1)
                self.assertEqual(self._idempotency_records(session, shop_id), 1)

    def test_database_default_is_read_committed(self):
        self.assertEqual(self.default_isolation_level, "read committed")


if __name__ == "__main__":
    unittest.main()
