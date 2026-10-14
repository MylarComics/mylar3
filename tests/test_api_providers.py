import json
import pytest
import mylar
from mylar import api

# Provider tuples as get_extras() loads them from config.ini:
# (name, host, verify, apikey, uid#categories, enabled, prov_id)
NEWZNABS = [
    ('DOGnzb (Prowlarr)', 'http://prowlarr:9696/5/api', '0', 'key5', '#7030', '1', 2),
    ('NZBgeek (Prowlarr)', 'http://prowlarr:9696/7/api', '0', 'key7', '#7030', '1', 4),
]
TORZNABS = [
    ('The Pirate Bay (Prowlarr)', 'http://prowlarr:9696/4/api', '0', 'key4', '7030', '1', 1),
]


@pytest.fixture
def providers(monkeypatch):
    monkeypatch.setattr(mylar, "CONFIG", mylar.config.Config("./nothing"))
    monkeypatch.setattr(mylar.CONFIG, "EXTRA_NEWZNABS", list(NEWZNABS), raising=False)
    monkeypatch.setattr(mylar.CONFIG, "EXTRA_TORZNABS", list(TORZNABS), raising=False)
    monkeypatch.setattr(mylar.CONFIG, "writeconfig", lambda *args, **kwargs: None, raising=False)
    return mylar.CONFIG


def del_provider(**kwargs):
    a = api.Api()
    a._delProvider(**kwargs)
    return json.loads(a.data)


@pytest.mark.parametrize("name", [
    'DOGnzb (Prowlarr)',  # exact stored name, as Prowlarr sends it
    'dognzb (prowlarr)',
    'DOGNZB (PROWLARR)',
])
@pytest.mark.unit
def test_del_newznab_provider_by_name_ignores_case(providers, name):
    result = del_provider(name=name, providertype='newznab')

    assert result['success'] is True
    assert [p[0] for p in providers.EXTRA_NEWZNABS] == ['NZBgeek (Prowlarr)']
    assert providers.EXTRA_TORZNABS == TORZNABS


@pytest.mark.parametrize("name", [
    'The Pirate Bay (Prowlarr)',
    'the pirate bay (prowlarr)',
])
@pytest.mark.unit
def test_del_torznab_provider_by_name_ignores_case(providers, name):
    result = del_provider(name=name, providertype='torznab')

    assert result['success'] is True
    assert providers.EXTRA_TORZNABS == []
    assert providers.EXTRA_NEWZNABS == NEWZNABS


@pytest.mark.unit
def test_del_provider_by_id(providers):
    result = del_provider(prov_id='4', providertype='newznab')

    assert result['success'] is True
    assert [p[0] for p in providers.EXTRA_NEWZNABS] == ['DOGnzb (Prowlarr)']


@pytest.mark.unit
def test_del_unknown_provider_fails_and_keeps_list(providers):
    result = del_provider(name='NZBFinder (Prowlarr)', providertype='newznab')

    assert result['success'] is False
    assert providers.EXTRA_NEWZNABS == NEWZNABS
