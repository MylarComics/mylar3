from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    MYLAR_PORT: int = 8090
    SECRET_KEY: str = "placeholder_secret_key"
    LOG_LEVEL: str = "INFO"

    POSTGRES_USER: str = "mylar"
    POSTGRES_PASSWORD: str = "mylarpass"
    POSTGRES_DB: str = "mylar_new"
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    
    DATABASE_URL: str = "postgresql+asyncpg://mylar:mylarpass@postgres:5432/mylar_new"
    REDIS_URL: str = "redis://redis:6379/0"
    
    COMICVINE_API_KEY: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
