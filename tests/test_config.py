import pytest
from flask import Flask

from app import _configure_secret_key


def test_production_requires_secret_key():
    flask_app = Flask(__name__)

    with pytest.raises(RuntimeError, match='SECRET_KEY must be configured outside development') as exc_info:
        _configure_secret_key(flask_app, 'production', None)

    assert 'SECRET_KEY' in str(exc_info.value)


def test_production_accepts_configured_secret_key():
    flask_app = Flask(__name__)
    configured_key = 'test-only-secret-value'

    _configure_secret_key(flask_app, 'production', configured_key)

    assert flask_app.config['SECRET_KEY'] == configured_key


def test_development_generates_ephemeral_secret_when_missing():
    flask_app = Flask(__name__)

    _configure_secret_key(flask_app, 'development', None)

    assert isinstance(flask_app.config['SECRET_KEY'], str)
    assert len(flask_app.config['SECRET_KEY']) == 64
