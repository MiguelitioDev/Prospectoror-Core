import json

from prospector import app_json
from prospector.cli import main
from tests.test_cli import ambiente  # noqa: F401  (fixture compartilhada)


def _linha(lead_id, nome="Pousada A", nota=80):
    return {"_proto": "x", "ID": lead_id, "Nome": nome, "Chance de venda": nota,
            "Status contato": "", "Observações": "", "Valor fechado (R$)": "",
            "Nota Google (conferir)": ""}


def test_acrescenta_sem_duplicar_e_limpa_campos(tmp_path):
    arq = tmp_path / "leads.json"
    assert app_json.acrescentar(arq, [_linha("a"), _linha("b")], [], {"Data": "1"}, "2026-10-01T06:00:00") == 2
    assert app_json.acrescentar(arq, [_linha("b", nota=90), _linha("c")], [], {"Data": "2"}, "2026-10-08T06:00:00") == 1
    dados = json.loads(arq.read_text(encoding="utf-8"))
    assert [l["ID"] for l in dados["leads"]] == ["a", "b", "c"]
    b = dados["leads"][1]
    assert b["Chance de venda"] == 90
    assert b["Exportado em"] == "2026-10-01T06:00:00"   # mantém a data da 1ª exportação
    assert "_proto" not in b and "Status contato" not in b and "Observações" not in b
    assert len(dados["rodadas"]) == 2
    assert dados["atualizado"] == "2026-10-08T06:00:00"


def test_marca_aba_pesquisar(tmp_path):
    arq = tmp_path / "leads.json"
    app_json.acrescentar(arq, [], [_linha("z")], {}, "2026-10-01T06:00:00")
    assert json.loads(arq.read_text(encoding="utf-8"))["leads"][0]["Aba"] == "Pesquisar contato"


def test_json_corrompido_recomeca(tmp_path):
    arq = tmp_path / "leads.json"
    arq.write_text("{quebrado", encoding="utf-8")
    assert app_json.acrescentar(arq, [_linha("a")], [], {}, "t") == 1


def test_cli_grava_json_e_rodada_vazia(ambiente, tmp_path):
    arq = tmp_path / "app" / "leads.json"
    assert main(["buscar", "--uf", "CE", "--saida", str(ambiente.saida), "--json", str(arq)]) == 0
    dados = json.loads(arq.read_text(encoding="utf-8"))
    assert dados["leads"] and all(l.get("Preparar") for l in dados["leads"])
    qtd = len(dados["leads"])
    main(["buscar", "--uf", "CE", "--saida", str(ambiente.saida), "--json", str(arq)])
    dados2 = json.loads(arq.read_text(encoding="utf-8"))
    assert len(dados2["leads"]) == qtd          # nada repetido
    assert len(dados2["rodadas"]) == 2          # rodada vazia registrada
