from typing import Optional
from sqlmodel import SQLModel, Field

class FailedRelease(SQLModel, table=True):
    __tablename__ = "failed_release"

    id: Optional[int] = Field(default=None, primary_key=True)
    release_id: str = Field(index=True, unique=True)  # Download URL or torrent hash
    title: Optional[str] = None                       # Title of the release / filename
    provider: Optional[str] = None                    # Provider / Indexer name
    comic_id: str = Field(index=True)                 # ComicVine Comic ID
    issue_id: str = Field(index=True)                 # ComicVine Issue ID
    date_failed: str                                  # ISO 8601 timestamp string
