import pytest
import requests

from prospector import osm
from prospector.modelos import Municipio
from prospector.osm import (
    buscar_municipio,
    consultar_overpass,
    elemento_para_lead,
    montar_consulta_area,
)


class _FakeOverpassResponse:
    def __init__(self, status_code: int, payload, json_erro: bool = False):
        self.status_code = status_code
        self._payload = payload
        self._json_erro = json_erro

    def json(self):
        if self._json_erro:
            raise ValueError("JSON inválido")
        return self._payload


def responder(monkeypatch, status_code: int, payload, json_erro: bool = False):
    """Substitui requests.post por uma resposta fixa e anula time.sleep."""
    monkeypatch.setattr(osm.time, "sleep", lambda s: None)
    monkeypatch.setattr(
        requests,
        "post",
        lambda *a, **k: _FakeOverpassResponse(status_code, payload, json_erro=json_erro),
    )


@pytest.fixture
def mun_fortaleza():
    """Município de Fortaleza para testes de conversão de elementos OSM."""
    return Municipio(ibge="2304400", nome="Fortaleza", uf="CE", lat=-3.73, lng=-38.52, populacao=2574412)


def test_consulta_usa_codigo_ibge():
    q = montar_consulta_area("2304400", {"X": ['"amenity"="bar"']})
    assert 'area["IBGE:GEOCODIGO"="2304400"]["admin_level"="8"]->.a;' in q
    assert 'nwr["amenity"="bar"]["name"](area.a);' in q


def test_remark_de_erro_vira_none(monkeypatch):
    responder(monkeypatch, 200, {"elements": [{"type": "node", "id": 1}], "remark": "runtime error: Query timed out"})
    assert consultar_overpass("q") is None


def test_todos_servidores_falhando_vira_none(monkeypatch):
    responder(monkeypatch, 504, {})
    assert consultar_overpass("q") is None


def test_cidade_sem_empresas_vira_lista_vazia(monkeypatch):
    responder(monkeypatch, 200, {"elements": []})
    assert consultar_overpass("q") == []


def test_http_429_pula_para_proximo_servidor(monkeypatch):
    sleeps = []
    chamadas = []
    monkeypatch.setattr(osm.time, "sleep", lambda s: sleeps.append(s))

    def fake_post(url, data=None, headers=None, timeout=None):
        chamadas.append(url)
        if len(chamadas) == 1:
            return _FakeOverpassResponse(429, {})
        return _FakeOverpassResponse(200, {"elements": [{"type": "node", "id": 7}]})

    monkeypatch.setattr(requests, "post", fake_post)
    assert consultar_overpass("q") == [{"type": "node", "id": 7}]
    assert sleeps == [30]
    assert len(chamadas) == 2 and chamadas[0] != chamadas[1]


def test_json_invalido_conta_como_falha(monkeypatch):
    responder(monkeypatch, 200, None, json_erro=True)
    assert consultar_overpass("q") is None


def test_posto_de_informacao_da_prefeitura_e_ignorado(mun_fortaleza):
    el = {"type": "node", "id": 5, "lat": -3.7, "lon": -38.5,
          "tags": {"name": "Posto de Informação Turística", "tourism": "information",
                   "information": "office", "operator": "Prefeitura de Fortaleza"}}
    assert elemento_para_lead(el, mun_fortaleza) is None


def test_elemento_vira_lead(mun_fortaleza):
    el = {"type": "way", "id": 9, "center": {"lat": -3.7, "lon": -38.5},
          "tags": {"name": "Pousada Sol", "tourism": "guest_house", "phone": "085 99999-8888",
                   "website": "https://pousadasol.com.br"}}
    lead = elemento_para_lead(el, mun_fortaleza)
    assert lead.id == "osm:way/9" and lead.fonte == "OSM" and lead.tipo == "Pousada/Hotel"
    assert lead.telefone == "+5585999998888" and lead.whatsapp == "https://wa.me/5585999998888"
    assert lead.status_site == "A verificar" and (lead.lat, lead.lng) == (-3.7, -38.5)


def test_buscar_municipio_deduplica_e_descarta_none(monkeypatch, mun_fortaleza):
    responder(monkeypatch, 200, {"elements": [
        {"type": "node", "id": 1, "lat": 0.0, "lon": -38.5, "tags": {"name": "Bar Zero", "amenity": "bar"}},
        {"type": "node", "id": 1, "lat": 0.0, "lon": -38.5, "tags": {"name": "Bar Zero Dup", "amenity": "bar"}},
        {"type": "node", "id": 2, "tags": {"amenity": "bar"}},
    ]})
    leads = buscar_municipio(mun_fortaleza, {"Bar/Café": ['"amenity"="bar"']})
    assert len(leads) == 1
    assert leads[0].id == "osm:node/1" and leads[0].lat == 0.0
