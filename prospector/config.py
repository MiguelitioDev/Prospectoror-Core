# Ponto de partida para calcular a distância (Fortaleza)
BASE_LAT, BASE_LNG = -3.7319, -38.5267

LIMITE_PRESENCIAL_KM = 60    # até aqui: visita presencial
LIMITE_LIGACAO_KM = 400      # até aqui: ligação; acima disso: mensagem

RAIO_KM = 6  # raio de busca ao redor do centro de cada cidade

TIPOS = {
    "Pousada/Hotel": ['"tourism"~"^(guest_house|hotel|hostel|apartment)$"'],
    "Restaurante": ['"amenity"~"^(restaurant|fast_food)$"'],
    "Bar/Café": ['"amenity"~"^(bar|cafe|pub|ice_cream)$"'],
    "Agência/Passeio": ['"shop"="travel_agency"', '"office"="travel_agent"',
                        '"tourism"="information"]["information"="office"'],
    "Kitesurf/Esporte": ['"sport"~"kitesurfing|surfing|windsurfing"'],
    "Loja de roupa": ['"shop"~"^(clothes|swimwear|boutique)$"'],
}

# Pontos por tipo de negócio (máximo 10)
PESO_TIPO = {
    "Pousada/Hotel": 10, "Agência/Passeio": 10, "Kitesurf/Esporte": 9,
    "Restaurante": 7, "Loja de roupa": 6, "Bar/Café": 4, "Outro": 3,
}

# Valor alvo base do site por tipo de negócio (R$)
PRECO_BASE = {
    "Pousada/Hotel": 1500, "Agência/Passeio": 1400, "Kitesurf/Esporte": 1300,
    "Restaurante": 1000, "Loja de roupa": 1000, "Bar/Café": 900, "Outro": 900,
}
PRECO_MINIMO_ABSOLUTO = 800   # nunca venda abaixo disso
ANCORA = 1.40                 # oferta inicial = alvo x 1,40
DESCONTO_MAXIMO = 0.85        # mínimo = alvo x 0,85

# ---- Protótipo ou site final ----
# Site final pronto só para os leads mais quentes e mais fáceis de fechar,
# porque leva mais tempo. Os demais recebem um protótipo rápido.
NOTA_SITE_FINAL = 75     # nota mínima para já fazer o site final
NOTA_PROTOTIPO = 55      # abaixo disso: não preparar nada agora
LIMITE_FINAIS = 5        # máximo de sites finais por rodada (seu tempo é curto)
HORAS_PROTOTIPO = 2      # estimativa usando o modelo do nicho
HORAS_FINAL = 8

# O que mostrar em cada nicho
SITES = {
    "Pousada/Hotel": {
        "prototipo": "Página única: capa com foto, 3 quartos com fotos, "
                     "botão 'Reservar pelo WhatsApp' e mapa",
        "final": "Site de pousada: galeria por quarto com preços, reserva pelo "
                 "WhatsApp com datas e nº de hóspedes, comodidades, mapa, "
                 "avaliações, FAQ e versão em inglês/espanhol",
    },
    "Agência/Passeio": {
        "prototipo": "Página única: 3 passeios em cards com preço e duração, "
                     "botão 'Agendar pelo WhatsApp'",
        "final": "Catálogo de passeios: página por passeio com roteiro, preço, "
                 "duração e fotos, agendamento pelo WhatsApp, depoimentos e "
                 "versão em inglês/espanhol",
    },
    "Kitesurf/Esporte": {
        "prototipo": "Página única: capa de ação, pacotes de aula com preço "
                     "e botão 'Agendar aula'",
        "final": "Site de escola: aulas por nível, pacotes, aluguel de "
                 "equipamento, época de vento, instrutores, agendamento pelo "
                 "WhatsApp e versão em inglês",
    },
    "Restaurante": {
        "prototipo": "Página única: capa, cardápio resumido (6 pratos), "
                     "horário e botão 'Pedir/Reservar pelo WhatsApp'",
        "final": "Cardápio digital completo por categoria com preços, "
                 "reserva e pedido pelo WhatsApp, horários, galeria e mapa",
    },
    "Bar/Café": {
        "prototipo": "Página única: capa, destaques do cardápio, horário e "
                     "botão WhatsApp",
        "final": "Site com cardápio completo, agenda de eventos/música ao "
                 "vivo, galeria, horários e mapa",
    },
    "Loja de roupa": {
        "prototipo": "Vitrine com 6 produtos e botão 'Comprar pelo WhatsApp'",
        "final": "Catálogo por categoria e tamanho, pedido pelo WhatsApp, "
                 "feed do Instagram, trocas e entrega",
    },
    "Outro": {
        "prototipo": "Página única: capa, serviços, contato pelo WhatsApp e mapa",
        "final": "Site institucional: serviços, sobre, galeria, depoimentos, "
                 "contato pelo WhatsApp e mapa",
    },
}

VERIFICAR_SITES = True   # False deixa a busca mais rápida
SO_REDE_SOCIAL = ("instagram.com", "facebook.com", "linktr.ee", "wa.me",
                  "whatsapp.com", "linkin.bio", "bio.link", "tiktok.com")

SERVIDORES = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
HEADERS = {"User-Agent": "buscar-leads/1.0 (uso pessoal)"}

STOPWORDS_NOME = {
    "pousada", "hotel", "hostel", "restaurante", "bar", "cafe",
    "lanchonete", "loja", "ltda", "me", "eireli", "epp", "sa",
    "de", "da", "do", "das", "dos", "e", "o", "a",
}

UFS = [
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO",
    "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR",
    "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
]
IBGE_CACHE_DIAS = 30

