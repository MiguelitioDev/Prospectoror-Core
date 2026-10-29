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
    "https://overpass.private.coffee/api/interpreter",
]
HEADERS = {"User-Agent": "buscar-leads/1.0 (uso pessoal)"}
# Sites bloqueiam robôs (403); para conferir se o site abre, parecemos um navegador.
HEADERS_SITE = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9",
}
# Provedores de e-mail que não indicam o site da empresa
EMAIL_GRATUITO = {
    "gmail.com", "googlemail.com", "hotmail.com", "hotmail.com.br", "outlook.com",
    "outlook.com.br", "live.com", "msn.com", "yahoo.com", "yahoo.com.br", "ymail.com",
    "icloud.com", "me.com", "uol.com.br", "bol.com.br", "terra.com.br", "ig.com.br",
    "globo.com", "globomail.com", "oi.com.br", "r7.com", "zipmail.com.br",
    "protonmail.com", "proton.me", "aol.com", "gmx.com", "mail.com",
    "qq.com", "163.com", "126.com", "sina.com",
}
ORGAO_PUBLICO = r"prefeitura|secretaria|governo|setur|municipal"

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

STATUS_BLOQUEIO = {"Sem interesse", "Não contatar"}

STATUS_CONTATO = [
    "Mensagem enviada",
    "Respondeu",
    "Reunião marcada",
    "Proposta enviada",
    "Fechado",
    "Sem interesse",
    "Não contatar",
]

MENSAGEM_PADRAO = (
    "Olá! Vi a {nome} aqui em {cidade} e preparei uma ideia de site para vocês, "
    "com contato direto pelo WhatsApp. Posso te mostrar em 2 minutos?"
)

MENSAGENS = {
    "Pousada/Hotel": (
        "Olá! Vi a {nome} em {cidade} e montei um protótipo de site com fotos dos quartos "
        "e reserva pelo WhatsApp. Posso te mandar o link para você ver?"
    ),
    "Agência/Passeio": (
        "Olá! Vi a {nome} em {cidade} e preparei um protótipo de site com catálogo de passeios, "
        "preços e agendamento pelo WhatsApp. Posso te mostrar?"
    ),
    "Kitesurf/Esporte": (
        "Olá! Vi a {nome} em {cidade} e montei um protótipo de site com pacotes de aula "
        "e agendamento pelo WhatsApp. Posso te enviar para dar uma olhada?"
    ),
    "Restaurante": (
        "Olá! Vi o {nome} em {cidade} e preparei um protótipo de site com cardápio digital "
        "e pedido/reserva pelo WhatsApp. Posso te mostrar em 2 minutos?"
    ),
    "Bar/Café": (
        "Olá! Vi o {nome} em {cidade} e montei um protótipo de site com destaques do cardápio, "
        "horários e botão de WhatsApp. Posso te mandar o link?"
    ),
    "Loja de roupa": (
        "Olá! Vi a {nome} em {cidade} e preparei um protótipo de vitrine online com produtos "
        "e compra direta pelo WhatsApp. Posso te mostrar como ficou?"
    ),
    "Outro": MENSAGEM_PADRAO,
}

UFS_PADRAO = ["CE"]
MAX_MUNICIPIOS = 40
REVARRER_DIAS = 90
LIMITE_EXPORTAR = 300
LIMITE_SEM_CONTATO = 100
PASTA_SAIDA = "."
PASTA_DADOS = "dados"

RECEITA_WEBDAV = "https://arquivos.receitafederal.gov.br/public.php/webdav/"
RECEITA_TOKEN = "YggdBLfdninEJX9"

CNAE_TIPOS = {
    "5510801": "Pousada/Hotel",
    "5510802": "Pousada/Hotel",
    "5590601": "Pousada/Hotel",
    "5590603": "Pousada/Hotel",
    "5590699": "Pousada/Hotel",
    "5611201": "Restaurante",
    "5611203": "Bar/Café",
    "5611204": "Bar/Café",
    "5611205": "Bar/Café",
    "7911200": "Agência/Passeio",
    "7912100": "Agência/Passeio",
    "7990200": "Agência/Passeio",
    "8591100": "Kitesurf/Esporte",
    "7721700": "Kitesurf/Esporte",
    "4781400": "Loja de roupa",
}

REGEX_KITESURF = r"kite|surf|wind|sup\b|vela"

MESES_EMPRESA_NOVA = 18
BONUS_EMPRESA_NOVA = 8

