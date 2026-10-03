import types

import pytest

import mylar
from mylar import cv

RATE_JSON = b'{"error":"Rate limit exceeded.  Slow down cowboy.","limit":0,"offset":0,"number_of_page_results":0,"number_of_total_results":0,"status_code":107,"results":[]}'
RATE_XML_420 = (b'<?xml version="1.0" encoding="utf-8"?><response><error><![CDATA[Rate limit exceeded.  Slow down cowboy.]]></error>'
                b'<limit>0</limit><offset>0</offset><number_of_page_results>0</number_of_page_results>'
                b'<number_of_total_results>0</number_of_total_results><status_code>420</status_code><results></results></response>')
ABNORMAL = b'<html><head><title>Abnormal Traffic Detected</title></head><body>slow down</body></html>'
OK_XML = (b'<?xml version="1.0" encoding="utf-8"?><response><error>OK</error><limit>100</limit><offset>0</offset>'
          b'<number_of_page_results>1</number_of_page_results><number_of_total_results>1</number_of_total_results>'
          b'<status_code>1</status_code><results><issue><id>12345</id><issue_number>1</issue_number><name>Issue</name>'
          b'<volume><id>999</id><name>Test Series</name></volume></issue></results></response>')
BADKEY_XML = (b'<?xml version="1.0" encoding="utf-8"?><response><error>Invalid API Key</error><limit>0</limit><offset>0</offset>'
              b'<number_of_page_results>0</number_of_page_results><number_of_total_results>0</number_of_total_results>'
              b'<status_code>100</status_code><results></results></response>')


class FakeResponse:
    def __init__(self, status_code, content):
        self.status_code = status_code
        self.content = content

    def json(self):
        import json
        return json.loads(self.content)


class FakeClock:
    def __init__(self):
        self.now = 1000000.0
        self.slept = 0

    def time(self):
        return self.now

    def sleep(self, secs):
        self.now += secs
        self.slept += secs


@pytest.fixture
def cvenv(monkeypatch):
    clock = FakeClock()
    fake_time = types.SimpleNamespace(time=clock.time, sleep=clock.sleep)
    monkeypatch.setattr(cv, 'time', fake_time)
    monkeypatch.setattr(mylar, 'CONFIG', types.SimpleNamespace(CVAPI_RATE=2, CV_VERIFY=True, COMICVINE_API='abc', CV_ONLY=True), raising=False)
    monkeypatch.setattr(mylar, 'CVURL', 'https://comicvine.gamespot.com/api/', raising=False)
    monkeypatch.setattr(mylar, 'CV_HEADERS', {}, raising=False)
    monkeypatch.setattr(mylar, 'SIGNAL', None, raising=False)
    yield clock


def queue_responses(monkeypatch, responses):
    calls = []

    def fake_get(url, params=None, verify=None, headers=None, timeout=None):
        calls.append(url)
        return responses.pop(0)
    monkeypatch.setattr(cv.requests, 'get', fake_get)
    return calls


@pytest.mark.unit
@pytest.mark.parametrize('response,expected', [
    (FakeResponse(420, RATE_JSON), 'HTTP 420'),
    (FakeResponse(200, RATE_JSON), 'Rate limit exceeded'),
    (FakeResponse(200, RATE_XML_420), 'Rate limit exceeded'),
    (FakeResponse(200, ABNORMAL), 'Abnormal Traffic Detected'),
    (FakeResponse(200, OK_XML), None),
    (FakeResponse(200, BADKEY_XML), None),
])
def test_ratelimit_reason(response, expected):
    assert cv.ratelimit_reason(response) == expected


@pytest.mark.unit
def test_cv_request_waits_and_retries(cvenv, monkeypatch):
    calls = queue_responses(monkeypatch, [FakeResponse(420, RATE_JSON),
                                          FakeResponse(200, RATE_XML_420),
                                          FakeResponse(200, ABNORMAL),
                                          FakeResponse(200, OK_XML)])
    r = cv.cv_request('https://comicvine.gamespot.com/api/issues/?api_key=abc&format=xml')
    assert r.content == OK_XML
    assert len(calls) == 4
    assert cvenv.slept == sum(cv.RATELIMIT_WAITS[:3]) + 4 * 2


@pytest.mark.unit
def test_pulldetails_never_returns_ratelimited_data(cvenv, monkeypatch):
    queue_responses(monkeypatch, [FakeResponse(420, RATE_XML_420), FakeResponse(200, OK_XML)])
    dom = cv.pulldetails(None, 'import', offset=0, comicidlist='12345')
    assert dom.getElementsByTagName('number_of_total_results')[0].firstChild.wholeText == '1'
    found = cv.GetImportList(dom)
    assert found == [{'ComicID': '999', 'IssueID': '12345', 'ComicName': 'Test Series', 'Issue_Name': 'Issue', 'Issue_Number': '1'}]


@pytest.mark.unit
def test_pulldetails_cv_error_is_not_empty_result(cvenv, monkeypatch):
    queue_responses(monkeypatch, [FakeResponse(200, BADKEY_XML)])
    assert cv.pulldetails(None, 'import', offset=0, comicidlist='12345') is None


@pytest.mark.unit
def test_wait_aborts_on_shutdown(cvenv, monkeypatch):
    queue_responses(monkeypatch, [FakeResponse(420, RATE_JSON)])
    monkeypatch.setattr(mylar, 'SIGNAL', 'shutdown', raising=False)
    with pytest.raises(cv.CVRateLimitAbort):
        cv.cv_request('https://comicvine.gamespot.com/api/volume/4050-1/?api_key=abc')


@pytest.mark.unit
def test_backoff_caps_at_an_hour(cvenv, monkeypatch):
    responses = [FakeResponse(420, RATE_JSON) for x in range(9)] + [FakeResponse(200, OK_XML)]
    queue_responses(monkeypatch, responses)
    cv.cv_request('https://comicvine.gamespot.com/api/issues/?api_key=abc')
    expected = sum(cv.RATELIMIT_WAITS) + 3 * cv.RATELIMIT_WAITS[-1] + 10 * 2
    assert cvenv.slept == expected
