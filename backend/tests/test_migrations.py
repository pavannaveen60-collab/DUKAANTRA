import io
import unittest
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory


BACKEND_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_CONFIG = BACKEND_DIR / "alembic.ini"
BASELINE_REVISION = "202611110001"
SHOP_PHONE_REVISION = "202611110002"
ORDER_IDEMPOTENCY_REVISION = "202611110003"
EXPECTED_TABLES = {
    "users",
    "shops",
    "products",
    "customers",
    "inventory",
    "orders",
    "order_items",
    "payments",
    "inventory_movements",
    "agent_tasks",
    "order_idempotency",
}


class MigrationConfigurationTests(unittest.TestCase):
    def make_config(self, output=None):
        return Config(
            str(ALEMBIC_CONFIG),
            output_buffer=output,
        )

    def test_revision_graph_has_baseline_then_shop_phone(self):
        revisions = ScriptDirectory.from_config(
            self.make_config()
        ).get_revisions("heads")

        self.assertEqual(len(revisions), 1)
        self.assertEqual(revisions[0].revision, ORDER_IDEMPOTENCY_REVISION)
        self.assertEqual(revisions[0].down_revision, SHOP_PHONE_REVISION)

    def test_offline_upgrade_sql_contains_all_baseline_tables_and_phone(self):
        output = io.StringIO()
        command.upgrade(
            self.make_config(output),
            "head",
            sql=True,
        )
        generated_sql = output.getvalue().lower()

        for table_name in EXPECTED_TABLES:
            with self.subTest(table=table_name):
                self.assertIn(f"create table {table_name}", generated_sql)

        shop_table_sql = generated_sql.split("create table shops (", 1)[1].split(
            ");",
            1,
        )[0]
        self.assertNotIn("phone", shop_table_sql)
        self.assertLess(
            generated_sql.index("create table shops"),
            generated_sql.index("alter table shops add column phone varchar(20)"),
        )
        self.assertIn("create unique index ix_users_email", generated_sql)
        self.assertIn(
            "constraint uq_inventory_shop_product unique (shop_id, product_id)",
            generated_sql,
        )
        self.assertIn("alter table shops add column phone varchar(20)", generated_sql)
        self.assertIn("create table alembic_version", generated_sql)
        self.assertIn("create table order_idempotency", generated_sql)
        self.assertIn(
            "constraint uq_order_idempotency_scope_key "
            "unique (user_id, shop_id, operation, key_hash)",
            generated_sql,
        )

    def test_schema_initializer_refuses_to_bypass_migrations(self):
        from init_db import initialize_database

        with self.assertRaisesRegex(RuntimeError, "alembic.*upgrade head"):
            initialize_database()


if __name__ == "__main__":
    unittest.main()
