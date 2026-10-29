import requests

from prospector import sites
from prospector.sites import checar_site, dominio_do_email, verificar_sites


class _FakeResp:
    def __init__(self, status_code: int):
        self.status_code = status_code

    def close(self):
        pass


def _rede(monkeypatch, respostas, dns=True):
    """Troca requests.get e o DNS por versões falsas; devolve a lista de chamadas feitas."""
    chamadas = []

    def fake_get(url, headers=None, timeout=None, stream=True, verify=True, allow_redirects=True):
        chamadas.append({"url": url, "headers": headers, "verify": verify})
        resposta = respostas(url, verify) if callable(respostas) else respostas.get(url)
        if resposta is None:
            raise requests.ConnectionError("recusada")
        if isinstance(resposta, Exception):
            raise resposta
        return _FakeResp(resposta)

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(sites, "_dns_resolve", lambda host: dns)
    return chamadas


def test_dominio_do_email_so_aceita_dominio_proprio():
    assert dominio_do_email("jeferson@expressomanini.com.br") == "expressomanini.com.br"
    assert dominio_do_email("  Contato@Pousada.COM.br ") == "pousada.com.br"
    assert dominio_do_email("alguem@gmail.com") == ""
    assert dominio_do_email("alguem@hotmail.com.br") == ""
    assert dominio_do_email("sem-arroba") == ""
    assert dominio_do_email("alguem@qq.com") == ""
    assert dominio_do_email("turismo@sjc.sp.gov.br") == ""   # órgão público: não é o site da empresa
    assert dominio_do_email("") == ""
    assert dominio_do_email(None) == ""


def test_checar_site_tenta_https_quando_http_falha(monkeypatch):
    _rede(monkeypatch, {"https://exemplo.com.br": 200})
    assert checar_site("http://exemplo.com.br") == "Tem site"


def test_checar_site_tenta_com_e_sem_www(monkeypatch):
    _rede(monkeypatch, {"https://www.exemplo.com.br": 200})
    assert checar_site("https://exemplo.com.br") == "Tem site"
    _rede(monkeypatch, {"https://exemplo.com.br": 200})
    assert checar_site("https://www.exemplo.com.br") == "Tem site"


def test_checar_site_adiciona_esquema_quando_falta(monkeypatch):
    chamadas = _rede(monkeypatch, {"https://exemplo.com.br": 200})
    assert checar_site("exemplo.com.br") == "Tem site"
    assert chamadas[0]["url"].startswith("http")


def test_checar_site_com_certificado_quebrado_esta_no_ar(monkeypatch):
    def resposta(url, verify):
        return requests.exceptions.SSLError("certificado vencido") if verify else 200

    _rede(monkeypatch, resposta)
    assert checar_site("https://exemplo.com.br") == "Tem site"


def test_checar_site_usa_user_agent_de_navegador(monkeypatch):
    chamadas = _rede(monkeypatch, {"https://exemplo.com.br": 200})
    checar_site("https://exemplo.com.br")
    assert "Mozilla" in chamadas[0]["headers"]["User-Agent"]


def test_checar_site_pagina_interna_404_mas_dominio_responde(monkeypatch):
    _rede(monkeypatch, {"https://exemplo.com.br/salvador/": 404, "https://exemplo.com.br": 200})
    assert checar_site("https://exemplo.com.br/salvador/") == "Tem site"


def test_checar_site_bloqueio_403_nao_e_fora_do_ar(monkeypatch):
    _rede(monkeypatch, lambda url, verify: 403)
    assert checar_site("https://exemplo.com.br") == "Não confirmado"


def test_checar_site_erro_503_nao_e_fora_do_ar(monkeypatch):
    _rede(monkeypatch, lambda url, verify: 503)
    assert checar_site("https://exemplo.com.br") == "Não confirmado"


def test_checar_site_timeout_nao_e_fora_do_ar(monkeypatch):
    _rede(monkeypatch, lambda url, verify: requests.Timeout("lento"))
    assert checar_site("https://exemplo.com.br") == "Não confirmado"


def test_checar_site_dominio_inexistente_esta_fora_do_ar(monkeypatch):
    chamadas = _rede(monkeypatch, lambda url, verify: 200, dns=False)
    assert checar_site("https://exemplo.com.br") == "Site fora do ar"
    assert chamadas == []


def test_checar_site_dns_com_falha_temporaria_nao_condena(monkeypatch):
    _rede(monkeypatch, lambda url, verify: None, dns=None)
    assert checar_site("https://exemplo.com.br") == "Não confirmado"


def test_checar_site_conexao_recusada_em_tudo_esta_fora_do_ar(monkeypatch):
    _rede(monkeypatch, lambda url, verify: None)
    assert checar_site("https://exemplo.com.br") == "Site fora do ar"


def test_checar_site_vazio_esta_fora_do_ar(monkeypatch):
    chamadas = _rede(monkeypatch, lambda url, verify: 200)
    assert checar_site("") == "Site fora do ar"
    assert checar_site(None) == "Site fora do ar"
    assert chamadas == []


def test_verifica_so_a_verificar(monkeypatch, fazer_lead):
    resultados = {"https://ok.com": "Tem site", "https://talvez.com": "Não confirmado"}
    monkeypatch.setattr(sites, "checar_site", lambda url: resultados.get(url, "Site fora do ar"))
    leads = [fazer_lead(id="a", site="https://ok.com", status_site="A verificar"),
             fazer_lead(id="b", site="https://off.com", status_site="A verificar"),
             fazer_lead(id="c", site="https://talvez.com", status_site="A verificar"),
             fazer_lead(id="d", status_site="Sem site")]
    assert verificar_sites(leads) == 3
    assert [l.status_site for l in leads] == ["Tem site", "Site fora do ar", "Não confirmado", "Sem site"]


def test_sem_site_com_email_do_osm_de_dominio_proprio_ganha_site(monkeypatch, fazer_lead):
    # Caso Expresso Manini: o OSM não tem 'website', mas o e-mail revela o domínio.
    consultados = []

    def fake(url):
        consultados.append(url)
        return "Tem site"

    monkeypatch.setattr(sites, "checar_site", fake)
    lead = fazer_lead(status_site="Sem site", email="jeferson@expressomanini.com.br",
                      tags={"email": "jeferson@expressomanini.com.br"})
    assert verificar_sites([lead]) == 1
    assert consultados == ["https://expressomanini.com.br"]
    assert (lead.site, lead.status_site) == ("https://expressomanini.com.br", "Tem site")


def test_dominio_do_email_que_nao_responde_mantem_sem_site(monkeypatch, fazer_lead):
    monkeypatch.setattr(sites, "checar_site", lambda url: "Site fora do ar")
    lead = fazer_lead(status_site="Sem site", email="a@semsite.com.br", tags={"email": "a@semsite.com.br"})
    verificar_sites([lead])
    assert (lead.site, lead.status_site) == ("", "Sem site")


def test_dominio_do_email_nao_confirmado_mantem_sem_site(monkeypatch, fazer_lead):
    monkeypatch.setattr(sites, "checar_site", lambda url: "Não confirmado")
    lead = fazer_lead(status_site="Sem site", email="a@talvez.com.br", tags={"email": "a@talvez.com.br"})
    verificar_sites([lead])
    assert (lead.site, lead.status_site) == ("", "Sem site")


def test_email_de_provedor_gratuito_nao_gera_consulta(monkeypatch, fazer_lead):
    monkeypatch.setattr(sites, "checar_site", lambda url: (_ for _ in ()).throw(AssertionError(url)))
    lead = fazer_lead(status_site="Sem site", email="a@gmail.com", tags={"email": "a@gmail.com"})
    assert verificar_sites([lead]) == 0
    assert lead.status_site == "Sem site"


def test_email_so_da_receita_nao_gera_consulta(monkeypatch, fazer_lead):
    # O e-mail da Receita costuma ser do contador; só o e-mail do OSM indica o site da empresa.
    monkeypatch.setattr(sites, "checar_site", lambda url: (_ for _ in ()).throw(AssertionError(url)))
    lead = fazer_lead(fonte="OSM+Receita", status_site="Sem site", email="contador@escritorio.com.br", tags={})
    assert verificar_sites([lead]) == 0
    assert lead.status_site == "Sem site"
