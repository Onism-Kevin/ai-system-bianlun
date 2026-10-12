"""S1-1：应用配置（settings）。

从 backend/.env 读取五键（MODEL_BASE_URL / MODEL_API_KEY / MODEL_DEFAULT /
DATABASE_URL / JWT_SECRET），并提供 dev/test/demo 三环境的数据库切换。

约定：
- 真实密钥只存在于 backend/.env（已 gitignore），本模块不打印、不回显任何密钥；
- APP_ENV 决定连哪个 schema（sfb_dev / sfb_test / sfb_demo），默认 dev；
- DATABASE_URL 是"基准连接串"，其 schema 段会被 APP_ENV 覆盖，
  这样三环境共用同一份 host/port/密码配置。
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

EnvName = Literal["dev", "test", "demo"]

ENV_SCHEMAS: dict[str, str] = {
    "dev": "sfb_dev",
    "test": "sfb_test",
    "demo": "sfb_demo",
}

_BACKEND_DIR = __import__("pathlib").Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """.env 驱动的应用配置。"""

    model_config = SettingsConfigDict(
        env_file=str(_BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- 模型网关（OpenAI 兼容）---
    model_base_url: str
    model_api_key: SecretStr
    model_default: str

    # --- 数据库（基准连接串，schema 段会被 app_env 覆盖）---
    database_url: SecretStr

    # --- 应用 ---
    jwt_secret: SecretStr
    app_env: EnvName = "dev"

    def sqlalchemy_url(self):
        """按当前 app_env 重写 schema 段后的 URL **对象**（供 engine 使用）。

        重要：必须传 URL 对象而不是 render_as_string() 的字符串——
        SQLAlchemy 2.x 的 make_url 不再对密码做 percent-decode，字符串
        往返（渲染->重解析）会把引号转义后的密码原样传给 DBAPI，导致
        1045。URL 对象直接携带已解析的密码，无二次解析。
        日志/打印请用 sqlalchemy_url_masked()。
        """
        schema = ENV_SCHEMAS[self.app_env]
        return make_url(self.database_url.get_secret_value()).set(database=schema)

    def sqlalchemy_url_masked(self) -> str:
        """打码连接串（密码段为 ***），仅供日志与报告。"""
        return self.sqlalchemy_url().render_as_string(hide_password=True)


@lru_cache
def get_settings() -> Settings:
    """带缓存的全局 Settings（进程内单例；测试里可用 get_settings.cache_clear() 重置）。"""
    return Settings()


def database_url_for(env: EnvName, settings: Settings | None = None):
    """显式取某个环境的 URL **对象**（与 settings.app_env 无关），用于三环境连通性核对。"""
    s = settings or get_settings()
    schema = ENV_SCHEMAS[env]
    return make_url(s.database_url.get_secret_value()).set(database=schema)
