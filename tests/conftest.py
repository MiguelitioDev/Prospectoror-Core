import pytest
from prospector.modelos import Lead


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
