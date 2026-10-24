from pathlib import Path
import zipfile
import pytest
import requests

from prospector.cnpj import (
    construir_base,
    estabs_do_municipio,
    linha_para_estab,
    mapa_municipios,
    mes_mais_recente,
)
from prospector.modelos import Municipio


def linha_estab_exemplo(**campos) -> list[str]:
    """Monta uma lista de 30 campos no formato de Estabelecimentos da Receita."""
    padrao = {
        "cnpj_basico": "12345678",
        "cnpj_ordem": "0001",
        "cnpj_dv": "90",
        "identificador": "1",
        "nome": "HOTEL SOL",
        "situacao": "02",
        "data_situacao": "20251103",
        "motivo_situacao": "00",
        "cidade_exterior": "",
        "pais": "",
        "inicio": "20251103",
        "cnae": "5510801",
        "cnae_secundaria": "",
        "tipo_logradouro": "AVENIDA",
        "logradouro": "BEIRA MAR",
        "numero": "100",
        "complemento": "LOJA 1; BLOCO A",
        "bairro": "MEIRELES",
        "cep": "60165121",
        "uf": "CE",
        "municipio": "1389",
        "ddd1": "85",
        "tel1": "88776655",
        "ddd2": "",
        "tel2": "",
        "ddd_fax": "",
        "fax": "",
        "email": "CONTATO@SOL.COM",
        "situacao_especial": "",
        "data_situacao_especial": "",
    }
    padrao.update(campos)
    chaves_ordenadas = [
        "cnpj_basico", "cnpj_ordem", "cnpj_dv", "identificador", "nome",
        "situacao", "data_situacao", "motivo_situacao", "cidade_exterior", "pais",
        "inicio", "cnae", "cnae_secundaria", "tipo_logradouro", "logradouro",
        "numero", "complemento", "bairro", "cep", "uf",
        "municipio", "ddd1", "tel1", "ddd2", "tel2",
        "ddd_fax", "fax", "email", "situacao_especial", "data_situacao_especial",
    ]
    return [str(padrao[k]) for k in chaves_ordenadas]


def _formatar_linha_csv(campos: list[str]) -> str:
    """Formata uma lista de campos como linha CSV com ';' e aspas duplas."""
    escapados = [str(c).replace('"', '""') for c in campos]
    return ";".join(f'"{c}"' for c in escapados)


def responder_propfind(monkeypatch, itens: list[str]) -> None:
    """Substitui requests.request para devolver um XML WebDAV contendo os hrefs informados."""
    hrefs = "".join(f"<d:response><d:href>/public.php/webdav/{item}</d:href></d:response>" for item in itens)
    xml = f'<?xml version="1.0" encoding="utf-8"?><d:multistatus xmlns:d="DAV:">{hrefs}</d:multistatus>'

    class _FakeResp:
        status_code = 207
        text = xml

        def raise_for_status(self):
            return None

    monkeypatch.setattr(requests, "request", lambda *a, **k: _FakeResp())


@pytest.fixture
def muns() -> list[Municipio]:
    """Lista mínima de municípios do IBGE com Fortaleza/CE."""
    return [Municipio(ibge="2304400", nome="Fortaleza", uf="CE", lat=-3.73, lng=-38.52, populacao=2574412)]


@pytest.fixture
def zip_municipios(tmp_path: Path) -> Path:
    """Cria um Municipios.zip de teste em latin-1 com membro de nome oficial da Receita."""
    caminho = tmp_path / "Municipios.zip"
    conteudo = '"1389";"FORTALEZA"\r\n"9999";"CIDADE INEXISTENTE"\r\n'
    with zipfile.ZipFile(caminho, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("F.K03200$Z.D61010.MUNICCSV", conteudo.encode("latin-1"))
    return caminho


@pytest.fixture
def mapa(zip_municipios: Path, muns: list[Municipio]) -> dict[tuple[str, str], str]:
    """Mapa (codigo_receita, uf) -> ibge para os testes."""
    return mapa_municipios(zip_municipios, muns)


@pytest.fixture
def zip_estabs(tmp_path: Path) -> Path:
    """Cria um Estabelecimentos0.zip com 4 linhas (1 válida, 1 baixada, 1 CNAE fora, 1 sem nome)."""
    linhas = [
        linha_estab_exemplo(
            cnpj_basico="12345678",
            nome="HOTEL SOL",
            situacao="02",
            inicio="20251103",
            cnae="5510801",
            complemento="LOJA 1; BLOCO A",
            uf="CE",
            municipio="1389",
            ddd1="85",
            tel1="88776655",
            email="CONTATO@SOL.COM",
        ),
        linha_estab_exemplo(cnpj_basico="22345678", situacao="08", nome="HOTEL BAIXADO"),
        linha_estab_exemplo(cnpj_basico="32345678", cnae="6201501", nome="SOFTWARE LTDA"),
        linha_estab_exemplo(cnpj_basico="42345678", nome=""),
    ]
    texto = "\r\n".join(_formatar_linha_csv(l) for l in linhas) + "\r\n"
    caminho = tmp_path / "Estabelecimentos0.zip"
    with zipfile.ZipFile(caminho, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("K3241.K03200Y0.D61010.ESTABELE", texto.encode("latin-1"))
    return caminho


def test_mapa_por_uf(zip_municipios, muns):          # muns: Fortaleza/CE 2304400
    assert mapa_municipios(zip_municipios, muns)[("1389", "CE")] == "2304400"


def test_construir_base_filtra(zip_estabs, mapa, tmp_path):
    assert construir_base([zip_estabs], tmp_path / "cnpj.db", mapa) == 1
    e = estabs_do_municipio(tmp_path / "cnpj.db", "2304400")[0]
    assert (e.tipo, e.telefone, e.abertura, e.email) == ("Pousada/Hotel", "+5585988776655", "2025-11-03", "contato@sol.com")


def test_kitesurf_so_com_nome(mapa):
    # linha_estab_exemplo(**campos) -> list[str] de 30 campos (helper no próprio arquivo)
    assert linha_para_estab(linha_estab_exemplo(cnae="8591100", nome="ACADEMIA FORCA"), mapa) is None
    assert linha_para_estab(linha_estab_exemplo(cnae="8591100", nome="CUMBUCO KITE SCHOOL"), mapa).tipo == "Kitesurf/Esporte"


def test_mes_mais_recente(monkeypatch):
    responder_propfind(monkeypatch, ["2026-08/", "2026-10/", "2026-09/", "cnpj.tar.gz"])
    assert mes_mais_recente() == "2026-10"


def test_construir_base_duas_vezes_substitui_sem_duplicar(zip_estabs, mapa, tmp_path):
    caminho_db = tmp_path / "cnpj.db"
    assert construir_base([zip_estabs], caminho_db, mapa) == 1
    assert construir_base([zip_estabs], caminho_db, mapa) == 1
    assert len(estabs_do_municipio(caminho_db, "2304400")) == 1


def test_estabs_do_municipio_banco_inexistente(tmp_path):
    assert estabs_do_municipio(tmp_path / "nao_existe.db", "2304400") == []
