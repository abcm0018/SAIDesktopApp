from contextlib import contextmanager
from unittest.mock import MagicMock, patch
import bcrypt
import pytest

from src.domain.user import User
from src.services.auth_service import AuthService


def _hashed(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _make_user(employee_number="1234", password="secret", active=True, blocked=False, role="operator"):
    user = MagicMock(spec=User)
    user.employee_number = employee_number
    user.password = _hashed(password)
    user.active = active
    user.blocked = blocked
    user.role = role
    return user


@pytest.fixture
def db_manager():
    manager = MagicMock()

    @contextmanager
    def session_ctx():
        session = MagicMock()
        yield session

    manager.session = session_ctx
    return manager


@pytest.fixture
def auth_service(db_manager):
    return AuthService(db_manager)


def _patch_query(db_manager, user):
    """Replaces session context manager to return a session that queries the given user."""
    session = MagicMock()
    session.query.return_value.filter_by.return_value.first.return_value = user

    @contextmanager
    def session_ctx():
        yield session

    db_manager.session = session_ctx


class TestAutenticarUsuario:
    def test_valid_credentials_return_user(self, auth_service, db_manager):
        user = _make_user(password="secret")
        _patch_query(db_manager, user)
        result = auth_service.autenticar_usuario("1234", "secret")
        assert result is user

    def test_wrong_password_returns_none(self, auth_service, db_manager):
        user = _make_user(password="secret")
        _patch_query(db_manager, user)
        result = auth_service.autenticar_usuario("1234", "wrong")
        assert result is None

    def test_user_not_found_returns_none(self, auth_service, db_manager):
        _patch_query(db_manager, None)
        result = auth_service.autenticar_usuario("9999", "secret")
        assert result is None

    def test_inactive_user_returns_none(self, auth_service, db_manager):
        user = _make_user(password="secret", active=False)
        _patch_query(db_manager, user)
        result = auth_service.autenticar_usuario("1234", "secret")
        assert result is None

    def test_blocked_user_returns_none(self, auth_service, db_manager):
        user = _make_user(password="secret", blocked=True)
        _patch_query(db_manager, user)
        result = auth_service.autenticar_usuario("1234", "secret")
        assert result is None

    def test_db_exception_returns_none(self, auth_service, db_manager):
        @contextmanager
        def failing_session():
            raise RuntimeError("DB down")
            yield  # unreachable — makes it a generator

        db_manager.session = failing_session
        result = auth_service.autenticar_usuario("1234", "secret")
        assert result is None


class TestCerrarSesion:
    def test_cerrar_sesion_with_user_does_not_raise(self):
        user = _make_user()
        AuthService.cerrar_sesion(user)  # should not raise

    def test_cerrar_sesion_with_none_does_not_raise(self):
        AuthService.cerrar_sesion(None)  # should not raise
