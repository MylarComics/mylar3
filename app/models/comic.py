from typing import Optional
from sqlmodel import SQLModel, Field

class Comic(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    comic_id: str = Field(index=True, unique=True)
    comic_name: str
    comic_year: Optional[int] = None
    publisher: Optional[str] = None
    status: str = Field(default="Active")  # Active, Paused
    location: Optional[str] = None
