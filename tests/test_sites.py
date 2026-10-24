import requests

from prospector import sites
from prospector.sites import site_no_ar, verificar_sites


class _FakeResp:
    def __init__(self, status_code: int):
        self.status_code = status_code
        self.fechado = False

    def close(self):
        self.fechado = True


def test_verifica_so_a_verificar(monkeypatch, fazer_lead):
    monkeypatch.setattr(sites, "site_no_ar", lambda url: url == "https://ok.com")
    leads = [fazer_lead(id="a", site="https://ok.com", status_site="A verificar"),
             fazer_lead(id="b", site="https://off.com", status_site="A verificar"),
             fazer_lead(id="c", status_site="Sem site")]
    assert verificar_sites(leads) == 2
    assert [l.status_site for l in leads] == ["Tem site", "Site fora do ar", "Sem site"]


def test_site_no_ar_head_e_fallback_get(monkeypatch):
    chamadas = []

    def fake_head(url, headers=None, timeout=8, allow_redirects=True):
        chamadas.append(("HEAD", url))
        return _FakeResp(405 if "bloqueia-head" in url else 200)

    def fake_get(url, headers=None, timeout=8, stream=True):
        chamadas.append(("GET", url))
        return _FakeResp(200)

    monkeypatch.setattr(requests, "head", fake_head)
    monkeypatch.setattr(requests, "get", fake_get)

    assert site_no_ar("exemplo.com.br") is True
    assert site_no_ar("https://bloqueia-head.com.br") is True
    assert chamadas[0] == ("HEAD", "http://exemplo.com.br")
    assert chamadas[1] == ("HEAD", "https://bloqueia-head.com.br")
    assert chamadas[2] == ("GET", "https://bloqueia-head.com.br")


def test_site_no_ar_trata_erros_e_vazio(monkeypatch):
    def fake_head(url, **kwargs):
        raise requests.RequestException("falha de rede")

    monkeypatch.setattr(requests, "head", fake_head)
    assert site_no_ar("https://fora.com") is False
    assert site_no_ar("") is False
    assert site_no_ar(None) is False
