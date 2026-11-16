import types

import pytest

import mylar
from mylar import nzbget


def _history(status, destdir, filesize=311, downloaded=295):
    # an nzbget history record as returned by the history() API call
    return [{'NZBID': 42, 'Name': 'Example.Series.001.2025', 'NZBName': 'Example.Series.001.2025.nzb',
             'Status': status, 'FileSizeMB': filesize, 'DownloadedSizeMB': downloaded,
             'DestDir': destdir, 'DeleteStatus': 'NONE', 'Deleted': False,
             'ScriptStatuses': [], 'Parameters': []}]


def _historycheck(monkeypatch, history):
    monkeypatch.setattr(mylar, 'LOG_LEVEL', 0, raising=False)
    monkeypatch.setattr(mylar, 'CONFIG', types.SimpleNamespace(NZBGET_DIRECTORY=None), raising=False)
    client = nzbget.NZBGet.__new__(nzbget.NZBGet)  # skip __init__: no nzbget server to connect to
    client.server = types.SimpleNamespace(history=lambda _: history)
    return client.historycheck({'NZBID': 42, 'issueid': '1', 'comicid': '2', 'download_info': {}})


@pytest.mark.unit
def test_success_with_skipped_par2_volumes_is_accepted(monkeypatch, tmp_path):
    # ParCheck=auto: the par2 recovery volumes were not needed, so only 295 of the NZB's 311MB were downloaded
    result = _historycheck(monkeypatch, _history('SUCCESS/ALL', str(tmp_path)))
    assert result['status'] is True
    assert result['failed'] is False
    assert result['location'] == str(tmp_path)


@pytest.mark.unit
def test_non_success_status_is_not_accepted(monkeypatch, tmp_path):
    result = _historycheck(monkeypatch, _history('WARNING/DAMAGED', str(tmp_path), downloaded=311))
    assert result == {'status': 'file not found', 'failed': False}
