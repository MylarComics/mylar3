from typing import Optional
from sqlmodel import SQLModel, Field

class Issue(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    issue_id: str = Field(index=True, unique=True)
    comic_id: str = Field(index=True)
    issue_number: str
    issue_name: Optional[str] = None
    release_date: Optional[str] = None
    status: str = Field(default="Skipped")  # Wanted, Snatched, Downloaded, Skipped
