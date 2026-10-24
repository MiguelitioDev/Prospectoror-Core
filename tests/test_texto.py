import pytest
from prospector.texto import normalizar_nome, nucleo_nome, normalizar_telefone, link_whatsapp


def test_normalizar_nome():
    assert normalizar_nome("  Pousada Ôlá-Mar! ") == "pousada ola mar"


def test_nucleo_nome_tira_genericos():
    assert nucleo_nome("Restaurante do Zé Ltda") == "ze"
    assert nucleo_nome("Pousada") == ""


@pytest.mark.parametrize("bruto,ddd,esperado", [
    ("(85) 99999-8888", "", "+5585999998888"),
    ("+55 85 99999-8888", "", "+5585999998888"),
    ("085 99999-8888", "", "+5585999998888"),       # bug atual: zero de tronco
    ("(85) 3222-1111", "", "+558532221111"),
    ("+55 (54) 9 9988-7766; 3222-0000", "", "+5554999887766"),
    ("88776655", "85", "+5585988776655"),           # celular antigo sem o 9 (Receita)
    ("32221111", "85", "+558532221111"),
    ("abc", "", ""),
])
def test_normalizar_telefone(bruto, ddd, esperado):
    assert normalizar_telefone(bruto, ddd) == esperado


def test_link_whatsapp_so_celular():
    assert link_whatsapp("+5585999998888") == "https://wa.me/5585999998888"
    assert link_whatsapp("+558532221111") == ""
    assert link_whatsapp("") == ""
