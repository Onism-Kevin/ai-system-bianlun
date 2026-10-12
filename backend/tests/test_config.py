"""S1-1 单测：config 三环境 schema 切换 + 密钥打码（不触网不触库）。"""
from __future__ import annotations

import pytest
from sqlalchemy.engine import make_url

from app.core.config import ENV_SCHEMAS, Settings, database_url_for

BASE_URL = "mysql+pymysql://root:p%40ss@127.0.0.1:3306/sfb_dev?charset=utf8mb4"


def make_settings(app_env: str = "dev") -> Settings:
    return Settings(
        _env_file=None,  # 不读磁盘 .env，纯注入
        model_base_url="http://127.0.0.1:8326/v1",
        model_api_key="test-key",
        model_default="cline/deepseek/deepseek-v4-pro",
        database_url=BASE_URL,
        jwt_secret="test-secret",
        app_env=app_env,
    )


def test_env_schema_mapping():
    assert ENV_SCHEMAS == {"dev": "sfb_dev", "test": "sfb_test", "demo": "sfb_demo"}


@pytest.mark.parametrize("env,schema", [("dev", "sfb_dev"), ("test", "sfb_test"), ("demo", "sfb_demo")])
def test_sqlalchemy_url_switches_schema(env, schema):
    url = make_url(make_settings(env).sqlalchemy_url())
    assert url.database == schema
    # host/密码等非 schema 段保持不变
    assert url.host == "127.0.0.1" and url.port == 3306
    assert url.password == "p@ss"  # percent-decode 还原


def test_default_env_is_dev():
    assert make_settings().app_env == "dev"
    assert make_url(make_settings().sqlalchemy_url()).database == "sfb_dev"


def test_masked_url_hides_password():
    masked = make_settings("test").sqlalchemy_url_masked()
    assert "p@ss" not in masked and "***" in masked
    # 真实连接串仍含密码
    assert "p@ss" in make_settings("test").sqlalchemy_url()


def test_database_url_for_explicit_env():
    for env, schema in ENV_SCHEMAS.items():
        url = make_url(database_url_for(env, make_settings()))
        assert url.database == schema


def test_model_keys_readable():
    s = make_settings()
    assert s.model_base_url.endswith("/v1")
    assert s.model_api_key.get_secret_value() == "test-key"
    assert s.model_default == "cline/deepseek/deepseek-v4-pro"
