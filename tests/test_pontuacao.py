from datetime import date

from prospector.pontuacao import calcular_chance, calcular_preco, pontuar


def test_chance_pousada_completa():
    tags = {"tourism": "guest_house", "opening_hours": "24/7", "addr:street": "Rua X", "stars": "3"}
    nota, motivos = calcular_chance(tags, "Pousada/Hotel", "Sem site", "+55 85 99999-8888",
                                    "https://wa.me/5585999998888", "", "", "Presencial")
    assert nota == 85
    assert motivos == ["não tem site", "tem WhatsApp", "negócio bem estruturado",
                       "depende de turista reservando online", "dá para visitar pessoalmente"]


def test_chance_franquia_zera():
    nota, motivos = calcular_chance({"amenity": "restaurant", "brand": "X"}, "Restaurante",
                                    "Tem site", "", "", "a@b.com", "", "Mensagem")
    assert nota == 0
    assert "rede/franquia: decisão fora do local" in motivos


def test_chance_sem_contato_limitada_a_15():
    nota, motivos = calcular_chance({"amenity": "bar"}, "Bar/Café", "Sem site", "", "", "", "", "Ligação")
    assert nota == 15 and motivos[-1] == "sem contato público"


def test_preco_hotel_4_estrelas_fora_do_ar():
    assert calcular_preco({"tourism": "hotel", "stars": "4", "rooms": "20"},
                          "Pousada/Hotel", "Site fora do ar") == (3350, 2400, 2050)


def test_preco_cafe_com_site_respeita_minimo():
    assert calcular_preco({"amenity": "cafe"}, "Bar/Café", "Tem site") == (1150, 800, 800)


def test_pontuar_mantem_colunas_e_acrescenta_novas(fazer_lead):
    linha = pontuar(fazer_lead(whatsapp="https://wa.me/5585999998888", telefone="+5585999998888"))
    chaves = [k for k in linha if not k.startswith("_")]
    assert chaves[:8] == ["Chance de venda", "Prioridade", "Nome", "Tipo", "Cidade", "UF", "Preparar", "Protótipo"]
    assert chaves[-4:] == ["Fonte", "CNPJ", "Aberta em", "ID"]
    assert linha["Abrir conversa"].startswith("https://wa.me/5585999998888?text=Ol%C3%A1")


def test_pontuar_nao_conferido():
    nota, motivos = calcular_chance({}, "Restaurante", "Não conferido", "+558532221111", "", "", "", "Mensagem")
    assert "site não conferido (procure no Google)" in motivos


def test_pontuar_site_nao_confirmado(fazer_lead):
    args = ({}, "Restaurante", "Não confirmado", "+558532221111", "", "", "", "Mensagem")
    nota, motivos = calcular_chance(*args)
    sem_site, _ = calcular_chance({}, "Restaurante", "Sem site", "+558532221111", "", "", "", "Mensagem")
    assert "site não confirmado (conferir se abre antes de abordar)" in motivos
    assert 5 < nota < sem_site
    linha = pontuar(fazer_lead(site="https://x.com.br", status_site="Não confirmado",
                               telefone="+558532221111"))
    assert linha["Site"] == "Não confirmado"


def test_bonus_empresa_nova():
    args = ({}, "Restaurante", "Sem site", "+558532221111", "", "", "", "Mensagem")
    sem, _ = calcular_chance(*args)
    com, motivos = calcular_chance(*args, abertura="2026-01-10", hoje=date(2026, 10, 24))
    velha, _ = calcular_chance(*args, abertura="2020-01-10", hoje=date(2026, 10, 24))
    assert com == sem + 8 and velha == sem
    assert "empresa nova (aberta há menos de 18 meses)" in motivos


def test_bonus_empresa_nova_datas_invalidas_ou_futuras():
    args = ({}, "Restaurante", "Sem site", "+558532221111", "", "", "", "Mensagem")
    sem, _ = calcular_chance(*args)
    futura, _ = calcular_chance(*args, abertura="2027-01-01", hoje=date(2026, 10, 24))
    invalida, _ = calcular_chance(*args, abertura="data-invalida", hoje=date(2026, 10, 24))
    assert futura == sem and invalida == sem


