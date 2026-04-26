from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    TURSO_DATABASE_URL: str
    TURSO_AUTH_TOKEN: str

    CF_ACCOUNT_ID: str
    R2_ACCESS_KEY_ID: str
    R2_SECRET_ACCESS_KEY: str
    R2_BUCKET_NAME: str
    R2_PUBLIC_URL: str

    SECRET_KEY: str
    DASHBOARD_USERNAME: str
    DASHBOARD_PASSWORD: str

    TARGET_BASE_URL: str
    SCRAPE_INTERVAL_MINUTES: int = 60
    SCRAPE_MAX_PAGES: int = 0  # 0 = geen limiet

    class Config:
        env_file = ".env"


settings = Settings()
