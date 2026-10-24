import pytest
import requests
from prospector.ibge import achar_cidade, listar_municipios
from prospector.modelos import Municipio


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _FakeIBGE:
    def __init__(self):
        self.chamadas = []

    def get(self, url, headers=None, timeout=60):
        self.chamadas.append(url)
        if url.endswith("/localidades/estados"):
            return _FakeResponse([{"id": 23, "sigla": "CE", "nome": "Ceará"}])
        if "/localidades/estados/CE/municipios" in url:
            return _FakeResponse([
                {"id": 2304400, "nome": "Fortaleza"},
                {"id": 2303709, "nome": "Caucaia"},
            ])
        if "/malhas/estados/23/metadados" in url:
            return _FakeResponse([
                {"id": "2304400", "centroide": {"longitude": -38.528, "latitude": -3.7858}},
            ])
        if "/agregados/6579/" in url:
            return _FakeResponse([{
                "resultados": [{
                    "series": [
                        {"localidade": {"id": "2304400", "nome": "Fortaleza - CE"}, "serie": {"2026": "2574412"}},
                        {"localidade": {"id": "2303709", "nome": "Caucaia - CE"}, "serie": {"2026": "-"}},
                    ]
                }]
            }])
        return _FakeResponse([], status_code=404)


@pytest.fixture
def fake_ibge(monkeypatch):
    """Substitui requests.get por respostas simuladas da API do IBGE."""
    fake = _FakeIBGE()
    monkeypatch.setattr(requests, "get", fake.get)
    return fake


@pytest.fixture
def muns_ce():
    """Lista de municípios do Ceará para testes de busca por nome."""
    return [
        Municipio(ibge="2304400", nome="Fortaleza", uf="CE", lat=-3.7858, lng=-38.528, populacao=2574412),
        Municipio(ibge="2303709", nome="Caucaia", uf="CE", lat=-3.7361, lng=-38.6531, populacao=355679),
        Municipio(ibge="2307254", nome="Jijoca de Jericoacoara", uf="CE", lat=-2.793, lng=-40.512, populacao=25555),
    ]


def test_listar_municipios_junta_centroide_e_populacao(fake_ibge, tmp_path):
    muns = listar_municipios(["CE"], tmp_path)
    fort = next(m for m in muns if m.ibge == "2304400")
    assert (fort.nome, fort.uf, fort.lat, fort.lng, fort.populacao) == ("Fortaleza", "CE", -3.7858, -38.528, 2574412)
    cauc = next(m for m in muns if m.ibge == "2303709")
    assert (cauc.lat, cauc.lng, cauc.populacao) == (0.0, 0.0, 0)


def test_listar_municipios_usa_cache(fake_ibge, tmp_path):
    listar_municipios(["CE"], tmp_path)
    fake_ibge.chamadas.clear()
    listar_municipios(["CE"], tmp_path)
    assert fake_ibge.chamadas == []


def test_uf_invalida(tmp_path):
    with pytest.raises(ValueError, match="UF desconhecida: XX"):
        listar_municipios(["XX"], tmp_path)


@pytest.mark.parametrize("texto", ["Fortaleza/CE", "fortaleza - ce", "FORTALEZA CE"])
def test_achar_cidade(texto, muns_ce):
    assert achar_cidade(texto, muns_ce).ibge == "2304400"


def test_achar_cidade_nome_composto(muns_ce):
    assert achar_cidade("Jijoca de Jericoacoara/CE", muns_ce).ibge == "2307254"


def test_achar_cidade_inexistente(muns_ce):
    with pytest.raises(ValueError, match="Cidade não encontrada: Sobral/CE"):
        achar_cidade("Sobral/CE", muns_ce)
