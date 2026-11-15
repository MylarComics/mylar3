import logging

import pytest

from mylar import logger as mylar_logger

MASK = 'xUDONTNEEDTOKNOWTHISx'


@pytest.mark.unit
def test_logger_masks_keys_in_messages_and_tracebacks(caplog):
    log = logging.getLogger('mylar')
    with caplog.at_level(logging.DEBUG, logger='mylar'):
        log.info('I have matched 1 files: %s', [{'link': 'https://indexer.example/api?t=get&id=abc&apikey=SECRET1'}])
        log.debug('link: https://tracker.example/dl/1?passkey=SECRET2&x=1')
        try:
            raise ValueError('Max retries exceeded with url: /api?t=get&apikey=SECRET3')
        except ValueError:
            log.warning('Error fetching data', exc_info=True)
    assert 'SECRET' not in caplog.text
    assert 'apikey=%s' % MASK in caplog.text and 'passkey=%s&x=1' % MASK in caplog.text


@pytest.mark.unit
@pytest.mark.parametrize("line,expected", [
    ('https://x/api?t=get&id=1&apikey=S1', 'https://x/api?t=get&id=1&apikey=M'),
    ('https://x/api?API_KEY=S1&t=get', 'https://x/api?API_KEY=M&t=get'),
    ('https://x/rss?r=S1&i=1', 'https://x/rss?r=M&i=1'),
    ('https://x/dl?id=1&token=S1', 'https://x/dl?id=1&token=M'),
    ('https://x/dl?key=S1', 'https://x/dl?key=M'),
    ('https://x/torrent/passkey/S1/123.torrent', 'https://x/torrent/passkey/M/123.torrent'),
    ('https://x/apikey/S1', 'https://x/apikey/M'),
    # left alone: other params whose names merely end in r/key, path words like /r/, plain ids
    ('https://x/api?year=2023&monkey=1&hotkey=2', 'https://x/api?year=2023&monkey=1&hotkey=2'),
    ('https://forum.example/r/comics', 'https://forum.example/r/comics'),
    ('id=abc', 'id=abc'),
])
def test_redact_key_forms(line, expected):
    assert mylar_logger.redact(line) == expected.replace('=M', '=' + MASK).replace('/M', '/' + MASK)
