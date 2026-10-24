from prospector.pontuacao import calcular_chance, calcular_preco


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
