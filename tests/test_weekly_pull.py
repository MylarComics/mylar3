import pytest
import pytest_asyncio
import httpx
from unittest.mock import AsyncMock, patch
from sqlmodel import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import engine, init_db
from app.models.comic import Comic
from app.models.issue import Issue
from app.models.weekly import WeeklyPullList
from app.services.weekly_pull import WeeklyPullService

@pytest_asyncio.fixture(scope="function")
async def db_session():
    await init_db()
    async with AsyncSession(engine) as session:
        yield session
        await session.execute(delete(WeeklyPullList))
        await session.execute(delete(Issue))
        await session.execute(delete(Comic))
        await session.commit()
    await engine.dispose()

@pytest.mark.asyncio
async def test_weekly_pull_sync_and_match(db_session):
    # 1. Seed watched comic in DB
    comic = Comic(
        comic_id="11111",
        comic_name="Batman",
        comic_year=2016,
        publisher="DC Comics",
        status="Active",
        location="comics/DC Comics/Batman (2016)"
    )
    db_session.add(comic)
    await db_session.commit()

    # 2. Mock JSON response from walksoftly proxy
    mock_data = [
        {
            "series": "Batman",
            "issue": "#50",
            "publisher": "DC Comics",
            "shipdate": "2026-06-10",
            "comicid": 11111,
            "issueid": 99999,
            "volume": "Vol. 3",
            "seriesyear": "2016",
            "type": "Comic",
            "link": "https://leagueofcomicgeeks.com/comic/batman-50"
        },
        {
            "series": "Spider-Man",
            "issue": "#1",
            "publisher": "Marvel",
            "shipdate": "2026-06-10",
            "comicid": 22222,
            "issueid": 88888,
            "volume": "Vol. 1",
            "seriesyear": "2026",
            "type": "Comic",
            "link": "https://leagueofcomicgeeks.com/comic/spider-man-1"
        }
    ]

    # Instantiate service and mock HTTP client call
    service = WeeklyPullService(db_session)
    mock_response = httpx.Response(200, json=mock_data)
    
    with patch.object(service.client, 'get', AsyncMock(return_value=mock_response)) as mock_get:
        res = await service.fetch_and_sync(week=24, year=2026)
        
        # Verify proxy parameters were passed
        mock_get.assert_called_once_with(
            "https://walksoftly.itsaninja.party/newcomics.php",
            params={"week": "24", "year": "2026"}
        )
        
        # Verify response metrics
        assert res["status"] == "success"
        assert res["count"] == 2
        assert res["matched"] == 1
        assert res["new_issues"] == 1 # Batman #50 auto-added to Issue table

    # 3. Verify database updates
    # A. Verify weekly records
    stmt_weekly = select(WeeklyPullList).where(WeeklyPullList.weeknumber == 24)
    res_weekly = await db_session.execute(stmt_weekly)
    records = res_weekly.scalars().all()
    assert len(records) == 2
    
    batman_rec = next(r for r in records if r.comic == "Batman")
    spiderman_rec = next(r for r in records if r.comic == "Spider-Man")
    
    assert batman_rec.status == "Wanted"
    assert batman_rec.comic_id == "11111"
    
    assert spiderman_rec.status == "Skipped"
    assert spiderman_rec.comic_id == "22222"

    # B. Verify new issue auto-creation
    stmt_issue = select(Issue).where(Issue.issue_id == "99999")
    res_issue = await db_session.execute(stmt_issue)
    new_issue = res_issue.scalars().first()
    assert new_issue is not None
    assert new_issue.issue_number == "50"
    assert new_issue.status == "Wanted"
    assert new_issue.comic_id == "11111"

    await service.close()
