import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

from app.downloaders.factory import get_downloader
from app.downloaders.sabnzbd import SABnzbdDownloader
from app.downloaders.nzbget import NZBGetDownloader
from app.downloaders.qbittorrent import QBittorrentDownloader
from app.downloaders.transmission import TransmissionDownloader


# ---------------------------------------------------------------------------
# Factory tests
# ---------------------------------------------------------------------------

def test_factory_returns_sabnzbd():
    client = get_downloader("sabnzbd")
    assert isinstance(client, SABnzbdDownloader)

def test_factory_returns_nzbget():
    client = get_downloader("nzbget")
    assert isinstance(client, NZBGetDownloader)

def test_factory_returns_qbittorrent():
    client = get_downloader("qbittorrent")
    assert isinstance(client, QBittorrentDownloader)

def test_factory_returns_transmission():
    client = get_downloader("transmission")
    assert isinstance(client, TransmissionDownloader)

def test_factory_returns_none_for_none():
    client = get_downloader("none")
    assert client is None

def test_factory_returns_none_for_unknown():
    client = get_downloader("unknownclient")
    assert client is None


# ---------------------------------------------------------------------------
# SABnzbd tests
# ---------------------------------------------------------------------------

class TestSABnzbdDownloader:
    def _make_client(self):
        with patch("app.downloaders.sabnzbd.settings") as mock_settings:
            mock_settings.SABNZBD_URL = "http://localhost:8080"
            mock_settings.SABNZBD_API_KEY = "testapikey"
            mock_settings.SABNZBD_CATEGORY = "comics"
            return SABnzbdDownloader()

    @pytest.mark.asyncio
    async def test_test_connection_success(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.json.return_value = {"version": "3.7.0"}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_http

            result = await client.test_connection()
            assert result is True

    @pytest.mark.asyncio
    async def test_test_connection_failure(self):
        client = self._make_client()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.get = AsyncMock(side_effect=Exception("Connection refused"))
            mock_client_class.return_value = mock_http

            result = await client.test_connection()
            assert result is False

    @pytest.mark.asyncio
    async def test_add_download_success(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": True, "nzo_ids": ["SABnzb+1234abc"]}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_http

            job_id = await client.add_download("http://test.nzb/nzb.nzb", "Amazing Spider-Man 001")
            assert job_id == "SABnzb+1234abc"

    @pytest.mark.asyncio
    async def test_add_download_failure(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": False}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_http

            job_id = await client.add_download("http://test.nzb/bad.nzb", "Bad NZB")
            assert job_id is None

    @pytest.mark.asyncio
    async def test_get_status_from_history(self):
        client = self._make_client()

        empty_queue_resp = MagicMock()
        empty_queue_resp.json.return_value = {"queue": {"slots": []}}

        hist_resp = MagicMock()
        hist_resp.json.return_value = {
            "history": {
                "slots": [
                    {
                        "nzo_id": "SABnzb+abc",
                        "name": "Spider-Man 001",
                        "status": "Completed",
                        "storage": "/downloads/Spider-Man 001",
                    }
                ]
            }
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.get = AsyncMock(side_effect=[empty_queue_resp, hist_resp])
            mock_client_class.return_value = mock_http

            status = await client.get_status("SABnzb+abc")
            assert status is not None
            assert status["status"] == "Completed"
            assert status["location"] == "/downloads/Spider-Man 001"
            assert status["failed"] is False

    @pytest.mark.asyncio
    async def test_remove_job_success(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": True}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_http

            result = await client.remove_job("SABnzb+abc")
            assert result is True


# ---------------------------------------------------------------------------
# NZBGet tests
# ---------------------------------------------------------------------------

class TestNZBGetDownloader:
    def _make_client(self):
        with patch("app.downloaders.nzbget.settings") as mock_settings:
            mock_settings.NZBGET_URL = "http://localhost:6789"
            mock_settings.NZBGET_USERNAME = "nzbget"
            mock_settings.NZBGET_PASSWORD = "tegbzn6789"
            mock_settings.NZBGET_CATEGORY = "comics"
            return NZBGetDownloader()

    @pytest.mark.asyncio
    async def test_test_connection_success(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.json.return_value = {"version": "1.1", "result": "21.1", "error": None}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_http

            result = await client.test_connection()
            assert result is True

    @pytest.mark.asyncio
    async def test_add_download_success(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.json.return_value = {"version": "1.1", "result": 42, "error": None}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_http

            job_id = await client.add_download("http://test.nzb/nzb.nzb", "Batman 001")
            assert job_id == "42"

    @pytest.mark.asyncio
    async def test_add_download_failure(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.json.return_value = {"version": "1.1", "result": 0, "error": None}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_http

            job_id = await client.add_download("http://bad.nzb", "Bad")
            assert job_id is None

    @pytest.mark.asyncio
    async def test_get_status_from_history(self):
        client = self._make_client()

        empty_queue = MagicMock()
        empty_queue.json.return_value = {"version": "1.1", "result": [], "error": None}

        history_resp = MagicMock()
        history_resp.json.return_value = {
            "version": "1.1",
            "error": None,
            "result": [
                {
                    "NZBID": 42,
                    "Name": "Batman 001",
                    "Status": "SUCCESS",
                    "DestDir": "/downloads/Batman 001",
                }
            ]
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.post = AsyncMock(side_effect=[empty_queue, history_resp])
            mock_client_class.return_value = mock_http

            status = await client.get_status("42")
            assert status is not None
            assert status["status"] == "Completed"
            assert status["failed"] is False


# ---------------------------------------------------------------------------
# qBittorrent tests
# ---------------------------------------------------------------------------

class TestQBittorrentDownloader:
    def _make_client(self):
        with patch("app.downloaders.qbittorrent.settings") as mock_settings:
            mock_settings.QBITTORRENT_URL = "http://localhost:8080"
            mock_settings.QBITTORRENT_USERNAME = "admin"
            mock_settings.QBITTORRENT_PASSWORD = "adminadmin"
            mock_settings.QBITTORRENT_CATEGORY = "comics"
            return QBittorrentDownloader()

    @pytest.mark.asyncio
    async def test_test_connection_success(self):
        client = self._make_client()

        login_resp = MagicMock()
        login_resp.text = "Ok."
        version_resp = MagicMock()
        version_resp.text = "4.6.0"

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.post = AsyncMock(return_value=login_resp)
            mock_http.get = AsyncMock(return_value=version_resp)
            mock_client_class.return_value = mock_http

            result = await client.test_connection()
            assert result is True

    @pytest.mark.asyncio
    async def test_get_status_downloading(self):
        client = self._make_client()

        login_resp = MagicMock()
        login_resp.text = "Ok."
        status_resp = MagicMock()
        status_resp.json.return_value = [
            {
                "hash": "ABCD1234",
                "name": "Iron Man 001",
                "state": "downloading",
                "save_path": "/downloads/",
            }
        ]

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.post = AsyncMock(return_value=login_resp)
            mock_http.get = AsyncMock(return_value=status_resp)
            mock_client_class.return_value = mock_http

            status = await client.get_status("ABCD1234")
            assert status is not None
            assert status["status"] == "Downloading"
            assert status["failed"] is False

    @pytest.mark.asyncio
    async def test_get_status_completed(self):
        client = self._make_client()

        login_resp = MagicMock()
        login_resp.text = "Ok."
        status_resp = MagicMock()
        status_resp.json.return_value = [
            {
                "hash": "ABCD1234",
                "name": "Iron Man 001",
                "state": "uploading",
                "save_path": "/downloads/",
            }
        ]

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.post = AsyncMock(return_value=login_resp)
            mock_http.get = AsyncMock(return_value=status_resp)
            mock_client_class.return_value = mock_http

            status = await client.get_status("ABCD1234")
            assert status["status"] == "Completed"

    def test_extract_magnet_hash(self):
        magnet = "magnet:?xt=urn:btih:AABBCCDD11223344AABBCCDD11223344AABBCCDD&dn=test"
        result = QBittorrentDownloader._extract_magnet_hash(magnet)
        assert result == "AABBCCDD11223344AABBCCDD11223344AABBCCDD"

    def test_extract_magnet_hash_invalid(self):
        result = QBittorrentDownloader._extract_magnet_hash("not_a_magnet")
        assert result is None


# ---------------------------------------------------------------------------
# Transmission tests
# ---------------------------------------------------------------------------

class TestTransmissionDownloader:
    def _make_client(self):
        with patch("app.downloaders.transmission.settings") as mock_settings:
            mock_settings.TRANSMISSION_URL = "http://localhost:9091"
            mock_settings.TRANSMISSION_USERNAME = ""
            mock_settings.TRANSMISSION_PASSWORD = ""
            mock_settings.TRANSMISSION_DIRECTORY = "/downloads"
            return TransmissionDownloader()

    @pytest.mark.asyncio
    async def test_test_connection_success(self):
        client = self._make_client()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.json.return_value = {
            "result": "success",
            "arguments": {"version": "3.00"},
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_http

            result = await client.test_connection()
            assert result is True

    @pytest.mark.asyncio
    async def test_test_connection_with_csrf_retry(self):
        """Test that 409 CSRF response triggers a retry with session header."""
        client = self._make_client()

        csrf_response = MagicMock()
        csrf_response.status_code = 409
        csrf_response.headers = {"X-Transmission-Session-Id": "test_session_123"}
        csrf_response.json.return_value = {}

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.headers = {}
        success_response.json.return_value = {
            "result": "success",
            "arguments": {"version": "3.00"},
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.post = AsyncMock(side_effect=[csrf_response, success_response])
            mock_client_class.return_value = mock_http

            result = await client.test_connection()
            assert result is True
            assert client._session_id == "test_session_123"

    @pytest.mark.asyncio
    async def test_add_download_magnet(self):
        client = self._make_client()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.json.return_value = {
            "result": "success",
            "arguments": {
                "torrent-added": {
                    "hashString": "deadbeef1234",
                    "name": "Thor 001",
                    "id": 5,
                }
            },
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_http

            job_id = await client.add_download("magnet:?xt=urn:btih:deadbeef1234", "Thor 001")
            assert job_id == "deadbeef1234"

    @pytest.mark.asyncio
    async def test_get_status_downloading(self):
        client = self._make_client()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.json.return_value = {
            "result": "success",
            "arguments": {
                "torrents": [
                    {
                        "hashString": "deadbeef1234",
                        "name": "Thor 001",
                        "status": 4,  # Downloading
                        "downloadDir": "/downloads",
                        "percentDone": 0.5,
                        "error": 0,
                        "errorString": "",
                    }
                ]
            },
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_http

            status = await client.get_status("deadbeef1234")
            assert status is not None
            assert status["status"] == "Downloading"
            assert status["failed"] is False

    @pytest.mark.asyncio
    async def test_get_status_completed(self):
        client = self._make_client()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.json.return_value = {
            "result": "success",
            "arguments": {
                "torrents": [
                    {
                        "hashString": "deadbeef1234",
                        "name": "Thor 001",
                        "status": 6,  # Seeding
                        "downloadDir": "/downloads",
                        "percentDone": 1.0,
                        "error": 0,
                        "errorString": "",
                    }
                ]
            },
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_http

            status = await client.get_status("deadbeef1234")
            assert status["status"] == "Completed"
