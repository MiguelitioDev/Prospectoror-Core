from prospector.historico import (
    abrir,
    atualizar_status,
    importar_legado,
    marcar_exportados,
    marcar_varrido,
    municipios_varridos,
    nova_rodada,
    pendentes,
    salvar_leads,
)


def test_lead_novo_e_repetido(conn, fazer_lead):
    assert salvar_leads(conn, [fazer_lead(id="osm:node/1")], "2026-10-24T10:00:00") == 1
    assert salvar_leads(conn, [fazer_lead(id="osm:node/1")], "2026-10-25T10:00:00") == 0
    assert len(pendentes(conn)) == 1


def test_exportado_nao_volta(conn, fazer_lead):
    salvar_leads(conn, [fazer_lead(id="osm:node/1"), fazer_lead(id="osm:node/2")], "t")
    r = nova_rodada(conn, "leads_x.xlsx", {}, "t")
    marcar_exportados(conn, ["osm:node/1"], r, "t")
    salvar_leads(conn, [fazer_lead(id="osm:node/1")], "t2")      # achado de novo numa revarredura
    assert [l.id for l in pendentes(conn)] == ["osm:node/2"]


def test_revarredura_nao_apaga_contato_nem_status_verificado(conn, fazer_lead):
    salvar_leads(conn, [fazer_lead(id="osm:node/1", telefone="+5585999998888",
                                   site="https://a.com", status_site="Site fora do ar")], "t")
    salvar_leads(conn, [fazer_lead(id="osm:node/1", telefone="", site="https://a.com",
                                   status_site="A verificar")], "t2")
    l = pendentes(conn)[0]
    assert l.telefone == "+5585999998888" and l.status_site == "Site fora do ar"


def test_bloqueio_por_status(conn, fazer_lead):
    salvar_leads(conn, [fazer_lead(id="osm:node/1")], "t")
    assert atualizar_status(conn, [{"ID": "osm:node/1", "Status contato": "Não contatar"},
                                   {"ID": "nao-existe", "Status contato": "Fechado"},
                                   {"Status contato": "Fechado"}]) == 1
    assert pendentes(conn) == []


def test_legado_com_contato_bloqueia_mesmo_nome_e_uf(conn, fazer_lead):
    importar_legado(conn, [
        {"Nome": "Pousada Sol", "Cidade": "Cumbuco - CE", "Telefone": "(85) 3222-1111"},
        {"Nome": "Bar Sem Contato", "Cidade": "Cumbuco - CE"},
    ])
    salvar_leads(conn, [fazer_lead(id="osm:node/1", nome="POUSADA SOL", uf="CE"),
                        fazer_lead(id="osm:node/2", nome="Pousada Sol", uf="RN"),
                        fazer_lead(id="osm:node/3", nome="Bar Sem Contato", uf="CE")], "t")
    assert sorted(l.id for l in pendentes(conn)) == ["osm:node/2", "osm:node/3"]


def test_varreduras(conn):
    marcar_varrido(conn, "2304400", "osm", "2026-10-01T00:00:00")
    assert municipios_varridos(conn, "osm", "2026-07-01T00:00:00") == {"2304400"}
    assert municipios_varridos(conn, "osm", "2026-10-02T00:00:00") == set()


def test_reabrir_banco_preserva_dados(tmp_path, fazer_lead):
    caminho = tmp_path / "sub" / "prospector.db"
    c1 = abrir(caminho)
    salvar_leads(c1, [fazer_lead(id="osm:node/1", telefone="+5585999998888")], "2026-10-24T10:00:00")
    marcar_varrido(c1, "2304400", "osm", "2026-10-24T10:00:00")
    c1.close()

    c2 = abrir(caminho)
    try:
        lista = pendentes(c2)
        assert len(lista) == 1 and lista[0].id == "osm:node/1"
        assert municipios_varridos(c2, "osm", "2026-10-01T00:00:00") == {"2304400"}
    finally:
        c2.close()


def test_bloqueio_permanece_apos_mudar_status(conn, fazer_lead):
    salvar_leads(conn, [fazer_lead(id="osm:node/1")], "t")
    atualizar_status(conn, [{"ID": "osm:node/1", "Status contato": "Sem interesse"}])
    atualizar_status(conn, [{"ID": "osm:node/1", "Status contato": "Respondeu", "Valor fechado (R$)": 1500.0}])
    assert pendentes(conn) == []
    row = conn.execute("SELECT status_contato, valor_fechado, bloqueado FROM leads WHERE id = 'osm:node/1'").fetchone()
    assert row == ("Respondeu", "1500", 1)


def test_mesmo_lead_duas_vezes_na_mesma_lista_conta_um(conn, fazer_lead):
    l1 = fazer_lead(id="osm:node/1", fonte="OSM", telefone="")
    l2 = fazer_lead(id="osm:node/1", fonte="Receita", telefone="+5585999998888")
    assert salvar_leads(conn, [l1, l2], "t") == 1
    lista = pendentes(conn)
    assert len(lista) == 1
    assert lista[0].telefone == "+5585999998888" and lista[0].fonte == "OSM+Receita"
