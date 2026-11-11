import unittest
from hashlib import sha256
import uuid
from contextlib import contextmanager
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import DBAPIError, IntegrityError

from api.routes import orders as order_routes
from models.inventory import Inventory
from models.order import Order
from models.order_idempotency import OrderIdempotency
from models.order_item import OrderItem
from models.product import Product
from models.shop import Shop
from schemas.order import OrderCreate
from services.order_service import OrderIdempotencyConflict, create_order


class OrderInventoryLockOrderingTests(unittest.TestCase):
    def setUp(self):
        self.shop_id = uuid.uuid4()
        self.user_id = uuid.uuid4()
        self.shop = SimpleNamespace(id=self.shop_id, owner_id=self.user_id)
        self.shops = {self.shop_id: self.shop}
        self.user = SimpleNamespace(id=self.user_id)
        self.products = {}
        self.inventories = {}
        self.db = MagicMock()
        self.lock_queries = []
        self.idempotency_rows = []
        self.committed_idempotency = {}
        self.committed_orders = {}
        self.committed_items = []
        self.pending_orders = []
        self.pending_items = []

        def scalar(statement):
            entity = statement.column_descriptions[0]["entity"]
            if entity is Shop:
                params = self._query_params(statement)
                shop = self.shops.get(params["id_1"])
                return (
                    shop
                    if shop and shop.owner_id == params["owner_id_1"]
                    else None
                )
            if entity is OrderIdempotency:
                params = self._query_params(statement)
                scope = (
                    params["user_id_1"],
                    params["shop_id_1"],
                    params["operation_1"],
                    params["key_hash_1"],
                )
                return self.committed_idempotency.get(scope)
            if entity is Product:
                params = self._query_params(statement)
                product_id = params["id_1"]
                shop_id = params["shop_id_1"]
                product = self.products.get(product_id)
                return product if product and product.shop_id == shop_id else None
            if entity is Inventory:
                compiled = statement.compile(
                    dialect=postgresql.dialect(),
                    compile_kwargs={"literal_binds": True},
                )
                self.lock_queries.append((statement, compiled))
                params = self._query_params(statement)
                product_id = params["product_id_1"]
                inventory = self.inventories.get(product_id)
                return (
                    inventory
                    if inventory and inventory.shop_id == params["shop_id_1"]
                    else None
                )
            if entity is Order:
                params = self._query_params(statement)
                order = self.committed_orders.get(params["id_1"])
                return (
                    order
                    if order and order.shop_id == params["shop_id_1"]
                    else None
                )
            self.fail(f"Unexpected scalar query entity: {entity!r}")

        self.db.scalar.side_effect = scalar
        self.db.scalars.side_effect = self.scalars
        self.db.begin_nested.side_effect = self.savepoint
        self.db.add.side_effect = self.add
        self.db.flush.side_effect = self.flush
        self.db.commit.side_effect = self.commit
        self.db.rollback.side_effect = self.rollback

    @staticmethod
    def _query_params(statement):
        return statement.compile(dialect=postgresql.dialect()).params

    @contextmanager
    def savepoint(self):
        pending_count = len(self.idempotency_rows)
        try:
            yield
        except Exception:
            del self.idempotency_rows[pending_count:]
            raise

    def add(self, value):
        if isinstance(value, OrderIdempotency):
            self.idempotency_rows.append(value)
        elif isinstance(value, Order):
            self.pending_orders.append(value)
        elif isinstance(value, OrderItem):
            self.pending_items.append(value)

    def flush(self):
        for record in self.idempotency_rows:
            scope = (
                record.user_id,
                record.shop_id,
                record.operation,
                record.key_hash,
            )
            if scope in self.committed_idempotency:
                raise IntegrityError(
                    "duplicate idempotency key",
                    {},
                    RuntimeError("unique constraint"),
                )

    def commit(self):
        for record in self.idempotency_rows:
            scope = (
                record.user_id,
                record.shop_id,
                record.operation,
                record.key_hash,
            )
            self.committed_idempotency[scope] = record
        for order in self.pending_orders:
            self.committed_orders[order.id] = order
        self.committed_items.extend(self.pending_items)
        self.idempotency_rows.clear()
        self.pending_orders.clear()
        self.pending_items.clear()

    def rollback(self):
        self.idempotency_rows.clear()
        self.pending_orders.clear()
        self.pending_items.clear()

    def scalars(self, statement):
        entity = statement.column_descriptions[0]["entity"]
        if entity is OrderItem:
            order_id = self._query_params(statement)["order_id_1"]
            return SimpleNamespace(
                all=lambda: [
                    item
                    for item in self.committed_items + self.pending_items
                    if item.order_id == order_id
                ]
            )
        self.fail(f"Unexpected scalars query entity: {entity!r}")

    @classmethod
    def _query_value(cls, statement, name):
        return cls._query_params(statement)[name]

    def add_product(self, product_id, quantity=20, shop_id=None):
        shop_id = shop_id or self.shop_id
        product = SimpleNamespace(
            id=product_id,
            shop_id=shop_id,
            name=f"Product {product_id}",
            price=Decimal("2.50"),
            is_active=True,
        )
        inventory = SimpleNamespace(
            id=uuid.uuid4(),
            product_id=product_id,
            shop_id=shop_id,
            quantity=quantity,
        )
        self.products[product_id] = product
        self.inventories[product_id] = inventory
        return inventory

    def make_order(self, items):
        return OrderCreate(
            items=[
                {"product_id": product_id, "quantity": quantity}
                for product_id, quantity in items
            ]
        )

    def invoke(self, items, key="test-idempotency-key-0001"):
        return create_order(
            self.db,
            self.user,
            self.shop_id,
            self.make_order(items),
            key,
        )

    def test_orders_with_different_request_order_use_sorted_locks(self):
        lower_id = uuid.UUID(int=10)
        higher_id = uuid.UUID(int=20)
        lower_inventory = self.add_product(lower_id)
        higher_inventory = self.add_product(higher_id)

        self.invoke([(higher_id, 2), (lower_id, 3)])

        locked_ids = [
            self._query_value(statement, "product_id_1")
            for statement, _ in self.lock_queries
        ]
        self.assertEqual(locked_ids, [lower_id, higher_id])
        self.assertEqual(lower_inventory.quantity, 17)
        self.assertEqual(higher_inventory.quantity, 18)
        self.assertTrue(all("FOR UPDATE" in str(compiled) for _, compiled in self.lock_queries))
        self.db.commit.assert_called_once()

    def test_reversed_product_order_acquires_the_same_lock_order(self):
        lower_id = uuid.UUID(int=10)
        higher_id = uuid.UUID(int=20)
        self.add_product(lower_id)
        self.add_product(higher_id)
        request_orders = [
            [(lower_id, 1), (higher_id, 1)],
            [(higher_id, 1), (lower_id, 1)],
        ]

        lock_orders = []
        for index, request_items in enumerate(request_orders):
            self.lock_queries.clear()
            self.invoke(request_items, f"test-idempotency-key-{index:04d}")
            lock_orders.append(
                [
                    self._query_value(statement, "product_id_1")
                    for statement, _ in self.lock_queries
                ]
            )

        self.assertEqual(lock_orders, [[lower_id, higher_id]] * 2)

    def test_duplicate_product_lines_are_aggregated_before_locking(self):
        product_id = uuid.UUID(int=10)
        inventory = self.add_product(product_id)

        self.invoke([(product_id, 2), (product_id, 3)])

        self.assertEqual(len(self.lock_queries), 1)
        self.assertEqual(inventory.quantity, 15)

    def test_insufficient_stock_rolls_back_without_deduction(self):
        product_id = uuid.UUID(int=10)
        inventory = self.add_product(product_id, quantity=3)

        with self.assertRaisesRegex(ValueError, "Insufficient stock"):
            self.invoke([(product_id, 4)])

        self.assertEqual(inventory.quantity, 3)
        self.db.commit.assert_not_called()
        self.db.rollback.assert_called_once()

    def test_missing_product_is_rejected_and_rolled_back(self):
        missing_id = uuid.UUID(int=99)

        with self.assertRaisesRegex(ValueError, "not found or inactive"):
            self.invoke([(missing_id, 1)])

        shop_query = self.db.scalar.call_args_list[0].args[0]
        compiled_shop_query = str(
            shop_query.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )
        self.assertIn("owner_id", compiled_shop_query)
        self.assertIn(str(self.user_id), compiled_shop_query)

        product_query = self.db.scalar.call_args.args[0]
        compiled_query = str(
            product_query.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )
        self.assertIn(str(self.shop_id), compiled_query)
        self.assertEqual(self.lock_queries, [])
        self.db.rollback.assert_called_once()
        self.db.commit.assert_not_called()

    def test_other_shop_product_is_rejected_by_shop_scoped_query(self):
        foreign_product_id = uuid.UUID(int=99)
        self.products[foreign_product_id] = SimpleNamespace(
            id=foreign_product_id,
            shop_id=uuid.uuid4(),
            name="Foreign product",
            price=Decimal("1.00"),
            is_active=True,
        )

        with self.assertRaisesRegex(ValueError, "not found or inactive"):
            self.invoke([(foreign_product_id, 1)])

        product_query = self.db.scalar.call_args.args[0]
        compiled_query = str(
            product_query.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )
        self.assertIn(str(self.shop_id), compiled_query)
        self.assertEqual(self.lock_queries, [])
        self.db.rollback.assert_called_once()
        self.db.commit.assert_not_called()

    def test_commit_failure_rolls_back_order_transaction(self):
        product_id = uuid.UUID(int=10)
        self.add_product(product_id)
        self.db.commit.side_effect = RuntimeError("commit failed")

        with self.assertRaisesRegex(RuntimeError, "commit failed"):
            self.invoke([(product_id, 1)])

        self.db.rollback.assert_called_once()

    def test_same_key_and_canonical_same_payload_return_original_order(self):
        lower_id = uuid.UUID(int=10)
        higher_id = uuid.UUID(int=20)
        lower_inventory = self.add_product(lower_id)
        higher_inventory = self.add_product(higher_id)
        key = "order-submit-retry-001"

        original = self.invoke([(lower_id, 2), (higher_id, 1)], key)
        repeated = self.invoke([(higher_id, 1), (lower_id, 2)], key)

        self.assertEqual(repeated["id"], original["id"])
        self.assertEqual(repeated["order_number"], original["order_number"])
        self.assertEqual(len(repeated["items"]), len(original["items"]))
        self.assertEqual(lower_inventory.quantity, 18)
        self.assertEqual(higher_inventory.quantity, 19)
        self.assertEqual(self.db.commit.call_count, 1)

    def test_same_key_with_different_payload_is_conflict(self):
        product_id = uuid.UUID(int=10)
        self.add_product(product_id)
        key = "order-submit-retry-002"
        self.invoke([(product_id, 1)], key)

        with self.assertRaisesRegex(
            OrderIdempotencyConflict,
            "different order request",
        ):
            self.invoke([(product_id, 2)], key)

        self.assertEqual(self.db.commit.call_count, 1)

    def test_idempotency_key_is_hashed_before_storage(self):
        product_id = uuid.UUID(int=10)
        self.add_product(product_id)
        key = "order-submit-hash-check-009"

        self.invoke([(product_id, 1)], key)

        record = next(iter(self.committed_idempotency.values()))
        self.assertEqual(record.key_hash, sha256(key.encode("utf-8")).hexdigest())
        self.assertNotEqual(record.key_hash, key)
        self.assertEqual(len(record.request_hash), 64)

    def test_duplicate_key_conflict_returns_original_and_deducts_once(self):
        product_id = uuid.UUID(int=10)
        inventory = self.add_product(product_id)
        key = "order-submit-race-003"

        first = self.invoke([(product_id, 3)], key)
        second = self.invoke([(product_id, 3)], key)

        self.assertEqual(first["id"], second["id"])
        self.assertEqual(inventory.quantity, 17)
        self.assertEqual(self.db.commit.call_count, 1)

    def test_different_keys_create_separate_orders(self):
        product_id = uuid.UUID(int=10)
        inventory = self.add_product(product_id)

        first = self.invoke([(product_id, 2)], "order-submit-new-004")
        second = self.invoke([(product_id, 2)], "order-submit-new-005")

        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(inventory.quantity, 16)
        self.assertEqual(self.db.commit.call_count, 2)

    def test_failed_transaction_does_not_reserve_key(self):
        product_id = uuid.UUID(int=10)
        key = "order-submit-rollback-006"
        with self.assertRaisesRegex(ValueError, "not found or inactive"):
            self.invoke([(product_id, 1)], key)

        self.assertEqual(self.committed_idempotency, {})
        self.add_product(product_id)
        result = self.invoke([(product_id, 1)], key)

        self.assertIsNotNone(result["id"])
        self.assertEqual(len(self.committed_idempotency), 1)
        self.assertEqual(self.db.commit.call_count, 1)

    def test_same_key_is_scoped_to_shop_and_owner(self):
        product_id = uuid.UUID(int=10)
        self.add_product(product_id)
        key = "order-submit-scope-007"
        first = self.invoke([(product_id, 1)], key)

        other_shop_id = uuid.uuid4()
        self.shops[other_shop_id] = SimpleNamespace(
            id=other_shop_id,
            owner_id=self.user_id,
        )
        other_product_id = uuid.UUID(int=20)
        self.add_product(other_product_id, shop_id=other_shop_id)
        second = create_order(
            self.db,
            self.user,
            other_shop_id,
            self.make_order([(other_product_id, 1)]),
            key,
        )
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(len(self.committed_idempotency), 2)

        another_user = SimpleNamespace(id=uuid.uuid4())
        with self.assertRaisesRegex(ValueError, "Shop not found"):
            create_order(
                self.db,
                another_user,
                self.shop_id,
                self.make_order([(product_id, 1)]),
                key,
            )
        self.assertEqual(len(self.committed_idempotency), 2)


class OrderIdempotencyRouteTests(unittest.TestCase):
    def test_payload_conflict_maps_to_http_409(self):
        order_data = OrderCreate(
            items=[{"product_id": uuid.uuid4(), "quantity": 1}]
        )
        with patch.object(
            order_routes,
            "create_order",
            side_effect=OrderIdempotencyConflict(
                "Idempotency key was already used with a different order request."
            ),
        ):
            with self.assertRaises(order_routes.HTTPException) as raised:
                order_routes.create_new_order(
                    uuid.uuid4(),
                    order_data,
                    "order-submit-route-conflict-008",
                    MagicMock(),
                    SimpleNamespace(id=uuid.uuid4()),
                )

        self.assertEqual(raised.exception.status_code, 409)


class OrderSerializationRetryTests(unittest.TestCase):
    @staticmethod
    def serialization_failure():
        original = RuntimeError("serialization failure")
        original.sqlstate = "40001"
        return DBAPIError("statement", {}, original)

    def test_serialization_failure_retries_the_entire_order_transaction(self):
        db = MagicMock()
        user = SimpleNamespace(id=uuid.uuid4())
        shop_id = uuid.uuid4()

        with patch(
            "services.order_service._create_order_once",
            side_effect=[self.serialization_failure(), {"id": uuid.uuid4()}],
        ) as create_once:
            result = create_order(
                db,
                user,
                shop_id,
                OrderCreate(
                    items=[{"product_id": uuid.uuid4(), "quantity": 1}]
                ),
                "serialization-retry-key",
            )

        self.assertIn("id", result)
        self.assertEqual(create_once.call_count, 2)
        db.rollback.assert_called_once()

    def test_serialization_retry_is_bounded(self):
        db = MagicMock()
        user = SimpleNamespace(id=uuid.uuid4())
        shop_id = uuid.uuid4()

        with patch(
            "services.order_service._create_order_once",
            side_effect=[self.serialization_failure() for _ in range(3)],
        ) as create_once:
            with self.assertRaises(DBAPIError):
                create_order(
                    db,
                    user,
                    shop_id,
                    OrderCreate(
                        items=[{"product_id": uuid.uuid4(), "quantity": 1}]
                    ),
                    "serialization-retry-exhausted-key",
                )

        self.assertEqual(create_once.call_count, 3)
        self.assertEqual(db.rollback.call_count, 3)


if __name__ == "__main__":
    unittest.main()
