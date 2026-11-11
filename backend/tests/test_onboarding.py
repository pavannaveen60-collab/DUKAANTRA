import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from api.routes import auth as auth_routes
from api.routes import shops as shop_routes
from schemas.auth import UserLogin, UserRegister
from schemas.shop import ShopCreate
from services import auth_service, shop_service


class MerchantRegistrationTests(unittest.TestCase):
    def test_registration_creates_user_with_normalized_email_and_hash(self):
        db = Mock()
        db.scalar.return_value = None
        data = UserRegister(
            full_name="Test Merchant",
            email=" Merchant@Example.com ",
            password="secure-password",
        )

        with patch.object(auth_service, "hash_password", return_value="hashed"):
            result = auth_service.register_user(db, data)

        created_user = db.add.call_args.args[0]
        self.assertIs(result, created_user)
        self.assertEqual(created_user.email, "merchant@example.com")
        self.assertEqual(created_user.password_hash, "hashed")
        db.commit.assert_called_once()

    def test_duplicate_registration_is_reported_as_conflict(self):
        data = UserRegister(
            full_name="Test Merchant",
            email="merchant@example.com",
            password="secure-password",
        )

        with patch.object(
            auth_routes,
            "register_user",
            side_effect=ValueError("An account with this email already exists."),
        ):
            with self.assertRaises(HTTPException) as raised:
                auth_routes.register(data, Mock())

        self.assertEqual(raised.exception.status_code, 409)

    def test_login_succeeds_for_users_with_or_without_shops(self):
        credentials = UserLogin(
            email="merchant@example.com",
            password="secure-password",
        )

        for owned_shops in ([], [SimpleNamespace(id=uuid.uuid4())]):
            with self.subTest(shop_count=len(owned_shops)):
                user = SimpleNamespace(
                    id=uuid.uuid4(),
                    email="merchant@example.com",
                    password_hash="hashed",
                    shops=owned_shops,
                )
                db = Mock()
                db.scalar.return_value = user

                with patch.object(auth_service, "verify_password", return_value=True):
                    authenticated_user = auth_service.authenticate_user(
                        db,
                        credentials,
                    )

                self.assertIs(authenticated_user, user)

    def test_login_route_returns_token_for_users_with_or_without_shops(self):
        credentials = UserLogin(
            email="merchant@example.com",
            password="secure-password",
        )

        for owned_shops in ([], [SimpleNamespace(id=uuid.uuid4())]):
            with self.subTest(shop_count=len(owned_shops)):
                user = SimpleNamespace(shops=owned_shops)
                with (
                    patch.object(auth_routes, "authenticate_user", return_value=user),
                    patch.object(auth_routes, "create_user_token", return_value="token"),
                ):
                    response = auth_routes.login(credentials, Mock())

                self.assertEqual(response["access_token"], "token")
                self.assertIs(response["user"], user)


class ShopOwnershipTests(unittest.TestCase):
    @staticmethod
    def shop_data():
        return ShopCreate(
            shop_name="  Green Market  ",
            business_type=" Grocery ",
            phone="+1 (555) 123-4567",
            address="  123 Market Street  ",
        )

    def test_shop_creation_persists_shop_for_authenticated_owner(self):
        owner = SimpleNamespace(id=uuid.uuid4())
        db = Mock()

        created = shop_service.create_shop(db, owner, self.shop_data())

        self.assertIs(created, db.add.call_args.args[0])
        self.assertEqual(created.owner_id, owner.id)
        self.assertEqual(created.shop_name, "Green Market")
        self.assertEqual(created.business_type, "Grocery")
        self.assertEqual(created.phone, "+1 (555) 123-4567")
        self.assertEqual(created.address, "123 Market Street")
        db.commit.assert_called_once()

    def test_shop_creation_rolls_back_after_commit_failure(self):
        db = Mock()
        db.commit.side_effect = RuntimeError("database unavailable")

        with self.assertRaisesRegex(RuntimeError, "database unavailable"):
            shop_service.create_shop(
                db,
                SimpleNamespace(id=uuid.uuid4()),
                self.shop_data(),
            )

        db.rollback.assert_called_once()

    def test_shop_list_is_scoped_to_owner_and_supports_multiple_shops(self):
        owner_id = uuid.uuid4()
        shops = [SimpleNamespace(id=uuid.uuid4()), SimpleNamespace(id=uuid.uuid4())]
        db = Mock()
        db.scalars.return_value.all.return_value = shops

        result = shop_service.get_my_shops(db, SimpleNamespace(id=owner_id))

        self.assertEqual(result, shops)
        statement = db.scalars.call_args.args[0]
        sql = str(statement.compile(dialect=postgresql.dialect()))
        self.assertIn("shops.owner_id", sql)

    def test_shopless_account_receives_empty_owned_shop_list(self):
        db = Mock()
        db.scalars.return_value.all.return_value = []

        result = shop_service.get_my_shops(
            db,
            SimpleNamespace(id=uuid.uuid4()),
        )

        self.assertEqual(result, [])

    def test_foreign_shop_is_not_retrievable(self):
        db = Mock()
        db.scalar.return_value = None

        with self.assertRaises(HTTPException) as raised:
            shop_routes.retrieve_shop(
                uuid.uuid4(),
                db,
                SimpleNamespace(id=uuid.uuid4()),
            )

        self.assertEqual(raised.exception.status_code, 404)
        statement = db.scalar.call_args.args[0]
        sql = str(statement.compile(dialect=postgresql.dialect()))
        self.assertIn("shops.owner_id", sql)


if __name__ == "__main__":
    unittest.main()
