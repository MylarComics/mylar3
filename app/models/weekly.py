from typing import Optional
from sqlmodel import SQLModel, Field

class WeeklyPullList(SQLModel, table=True):
    __tablename__ = "weekly"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    shipdate: Optional[str] = None
    publisher: Optional[str] = None
    issue: Optional[str] = None
    comic: str
    extra: Optional[str] = None
    status: str = Field(default="Skipped")
    comic_id: Optional[str] = None
    issue_id: Optional[str] = None
    cv_last_update: Optional[str] = None
    dynamic_name: Optional[str] = None
    weeknumber: Optional[int] = None
    year: Optional[int] = None
    volume: Optional[str] = None
    seriesyear: Optional[str] = None
    annuallink: Optional[str] = None
    format: Optional[str] = None
