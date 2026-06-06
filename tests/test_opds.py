import os
import zipfile
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlmodel import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from PIL import Image
from io import BytesIO

from app.main import app
from app.core.db import engine, init_db, get_session
from app.models.comic import Comic
from app.models.issue import Issue
from app.core.config import settings

@pytest_asyncio.fixture(scope="function")
async def db_session():
    await init_db()
    async with AsyncSession(engine) as session:
        yield session
        await session.execute(delete(Issue))
        await session.execute(delete(Comic))
        await session.commit()
    await engine.dispose()

@pytest_asyncio.fixture(scope="function")
async def client(db_session):
    async def _get_session_override():
        yield db_session
    app.dependency_overrides[get_session] = _get_session_override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client
    app.dependency_overrides.pop(get_session, None)

@pytest.fixture(scope="function")
def mock_cbz(tmp_path):
    # Create a dummy cbz archive with 2 pages
    cbz_dir = tmp_path / "comics" / "Marvel" / "Amazing Fantasy (1962)"
    os.makedirs(cbz_dir, exist_ok=True)
    cbz_path = cbz_dir / "Amazing_Fantasy_015.cbz"

    # Create dummy images
    img1 = Image.new("RGB", (200, 300), color="blue")
    img2 = Image.new("RGB", (200, 300), color="red")

    out1 = BytesIO()
    img1.save(out1, format="JPEG")
    out2 = BytesIO()
    img2.save(out2, format="JPEG")

    with zipfile.ZipFile(cbz_path, "w") as z:
        z.writestr("page1.jpg", out1.getvalue())
        z.writestr("page2.jpg", out2.getvalue())

    return str(cbz_path), str(cbz_dir)

@pytest.mark.asyncio
async def test_opds_catalog_disabled(client):
    # Temporarily disable OPDS
    original_val = settings.OPDS_ENABLE
    settings.OPDS_ENABLE = False
    try:
        response = await client.get("/opds")
        assert response.status_code == 403
    finally:
        settings.OPDS_ENABLE = original_val

@pytest.mark.asyncio
async def test_opds_catalog_flow(client, db_session, mock_cbz):
    cbz_filepath, cbz_dirpath = mock_cbz

    # Seed Comic & Issue
    comic = Comic(
        comic_id="12345",
        comic_name="Amazing Fantasy",
        comic_year=1962,
        publisher="Marvel",
        status="Active",
        location=cbz_dirpath
    )
    issue = Issue(
        issue_id="67890",
        comic_id="12345",
        issue_number="15",
        issue_name="Spider-Man Debut",
        release_date="1962-08-10",
        status="Downloaded",
        location=os.path.basename(cbz_filepath)
    )
    db_session.add(comic)
    db_session.add(issue)
    await db_session.commit()

    # 1. Test cmd=root
    response = await client.get("/opds")
    assert response.status_code == 200
    assert "application/atom+xml" in response.headers["content-type"]
    xml_text = response.text
    assert "Mylar OPDS Catalog" in xml_text
    assert "cmd=Recent" in xml_text
    assert "cmd=Publishers" in xml_text
    assert "cmd=AllTitles" in xml_text

    # 2. Test cmd=Publishers
    response = await client.get("/opds?cmd=Publishers")
    assert response.status_code == 200
    assert "OPDS - Publishers" in response.text
    assert "publisher:Marvel" in response.text
    assert "cmd=Publisher" in response.text

    # 3. Test cmd=Publisher
    response = await client.get("/opds?cmd=Publisher&pubid=Marvel")
    assert response.status_code == 200
    assert "Publisher - Marvel" in response.text
    assert "comic:12345" in response.text

    # 4. Test cmd=AllTitles
    response = await client.get("/opds?cmd=AllTitles")
    assert response.status_code == 200
    assert "All Titles" in response.text
    assert "comic:12345" in response.text

    # 5. Test cmd=Comic
    response = await client.get("/opds?cmd=Comic&comicid=12345")
    assert response.status_code == 200
    assert "Series - Amazing Fantasy" in response.text
    assert "issue:67890" in response.text
    assert "pse:count=\"2\"" in response.text
    assert "cmd=Stream&amp;issueid=67890&amp;page=0&amp;width=300" in response.text

    # 6. Test cmd=Recent
    response = await client.get("/opds?cmd=Recent")
    assert response.status_code == 200
    assert "Recent Arrivals" in response.text
    assert "issue:67890" in response.text

    # 7. Test cmd=deliverFile (downloading full file)
    response = await client.get("/opds?cmd=deliverFile&issueid=67890")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/octet-stream"
    assert len(response.content) == os.path.getsize(cbz_filepath)

    # 8. Test cmd=Stream page 0 (original size)
    response = await client.get("/opds?cmd=Stream&issueid=67890&page=0")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert len(response.content) > 0

    # 9. Test cmd=Stream page 0 (resized)
    response = await client.get("/opds?cmd=Stream&issueid=67890&page=0&width=100")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    img = Image.open(BytesIO(response.content))
    assert img.size[0] == 100

    # 10. Test cmd=Stream page out of bounds
    response = await client.get("/opds?cmd=Stream&issueid=67890&page=2")
    assert response.status_code == 404
