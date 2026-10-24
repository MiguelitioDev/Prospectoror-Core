import pytest
from prospector import historico
from prospector.modelos import Estab, Lead


@pytest.fixture
def conn(tmp_path):
    """Abre um banco de histórico temporário para testes."""
    conexao = historico.abrir(tmp_path / "prospector.db")
    try:
        yield conexao
    finally:
        conexao.close()


@pytest.fixture
def fazer_lead():
    """Cria um Lead de teste com valores padrão substituíveis."""
    def _fazer(**campos) -> Lead:
        padroes = {
            "id": "osm:node/1",
            "fonte": "OSM",
            "nome": "Pousada Teste",
            "tipo": "Pousada/Hotel",
            "municipio_ibge": "2304400",
            "cidade": "Fortaleza",
            "uf": "CE",
            "lat": -3.73,
            "lng": -38.52,
            "status_site": "Sem site",
        }
        padroes.update(campos)
        return Lead(**padroes)
    return _fazer


@pytest.fixture
def fazer_estab():
    """Cria um Estab de teste com valores padrão coerentes com fazer_lead."""
    def _fazer(**campos) -> Estab:
        padroes = {
            "cnpj": "12345678000190",
            "nome": "POUSADA TESTE",
            "cnae": "5510801",
            "tipo": "Pousada/Hotel",
            "municipio_ibge": "2304400",
            "uf": "CE",
            "logradouro": "RUA A 100",
            "bairro": "CENTRO",
            "cep": "60000000",
            "telefone": "+5585999998888",
            "telefone2": "",
            "email": "contato@teste.com",
            "abertura": "2026-01-10",
        }
        padroes.update(campos)
        return Estab(**padroes)
    return _fazer
