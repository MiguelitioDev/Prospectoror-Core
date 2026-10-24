"""
Busca empresas no OpenStreetMap (API Overpass), calcula a chance de venda
e sugere o preço de cada site. Gera uma planilha de leads.

100% gratuito: sem chave, sem cadastro, sem cartão.

Como usar:
  1. pip install requests openpyxl
  2. Ajuste a CONFIGURAÇÃO abaixo, se quiser
  3. python buscar_leads.py

Como a chance de venda é calculada (0 a 100), só com dados públicos:
  - Necessidade (até 40): não ter site, ter só Instagram ou site fora do ar
  - Contato (até 20): ter WhatsApp, telefone, e-mail, rede social
  - Estrutura (até 20): horário, endereço, aceita cartão, estrelas, quartos
    -> negócio organizado costuma ter dinheiro e decidir rápido
  - Tipo de negócio (até 10): quem depende de turista reservando online
    (pousada, agência, kitesurf) sente mais falta de site
  - Distância (até 10): visita presencial fecha mais fácil que mensagem
  - Rede/franquia perde pontos: a decisão não é do dono local
  - Sem nenhum contato, a nota fica limitada: não dá para oferecer

A nota serve para ORDENAR quem abordar primeiro. Não é uma probabilidade
real. Depois dos primeiros 20 a 30 contatos, ajuste os PESOS conforme
quem de fato respondeu e comprou.

O que preparar para cada empresa (colunas "Protótipo" e "Site final"):
  - Site final: nota alta, dá para visitar ou ligar, e ainda sem site bom.
    Limitado a LIMITE_FINAIS por rodada, para caber no seu tempo.
  - Protótipo: os demais leads quentes e mornos.
  - Nada agora: leads frios (use só uma mensagem com demo do nicho).

Preço: parte do valor base do tipo de negócio e sobe com sinais de porte
(hotel, estrelas, muitos quartos, site anterior fora do ar). Gera:
  - Oferta inicial: o valor que você apresenta primeiro (âncora)
  - Valor alvo: onde a negociação deve terminar
  - Mínimo: não desça abaixo disso
"""

import math
import sys
import time
from datetime import datetime
from urllib.parse import quote_plus

import requests
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

# ---------------- CONFIGURAÇÃO ----------------

# Ponto de partida para calcular a distância (Fortaleza)
BASE_LAT, BASE_LNG = -3.7319, -38.5267

LIMITE_PRESENCIAL_KM = 60    # até aqui: visita presencial
LIMITE_LIGACAO_KM = 400      # até aqui: ligação; acima disso: mensagem

RAIO_KM = 6  # raio de busca ao redor do centro de cada cidade

CIDADES = {
    "Cumbuco - CE": (-3.627, -38.729),
    "Aquiraz - CE": (-3.901, -38.391),
    "Canoa Quebrada - CE": (-4.528, -37.693),
    "Jericoacoara - CE": (-2.797, -40.514),
    "Guaramiranga - CE": (-4.263, -38.932),
    "Pipa - RN": (-6.229, -35.048),
    "Porto de Galinhas - PE": (-8.503, -35.005),
    "Gramado - RS": (-29.379, -50.874),
}

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

ARQUIVO_SAIDA = f"leads_{datetime.now():%Y-%m-%d_%H%M}.xlsx"

# ----------------------------------------------


def montar_consulta(lat, lng):
    raio_m = int(RAIO_KM * 1000)
    partes = []
    for filtros in TIPOS.values():
        for f in filtros:
            partes.append(f'nwr[{f}]["name"](around:{raio_m},{lat},{lng});')
    return f"[out:json][timeout:90];({''.join(partes)});out center tags;"


def consultar_overpass(consulta):
    for url in SERVIDORES:
        for tentativa in range(2):
            try:
                r = requests.post(url, data={"data": consulta},
                                  headers=HEADERS, timeout=120)
                if r.status_code == 200:
                    return r.json().get("elements", [])
                print(f"  ! {url} respondeu {r.status_code}, tentando de novo...")
            except requests.RequestException as e:
                print(f"  ! Falha em {url}: {e}")
            time.sleep(5 * (tentativa + 1))
    return []


def identificar_tipo(tags):
    t, a, s = tags.get("tourism", ""), tags.get("amenity", ""), tags.get("shop", "")
    if t in ("guest_house", "hotel", "hostel", "apartment"):
        return "Pousada/Hotel"
    if a in ("restaurant", "fast_food"):
        return "Restaurante"
    if a in ("bar", "cafe", "pub", "ice_cream"):
        return "Bar/Café"
    if s == "travel_agency" or tags.get("office") == "travel_agent" or t == "information":
        return "Agência/Passeio"
    if any(x in tags.get("sport", "") for x in ("kite", "surf")):
        return "Kitesurf/Esporte"
    if s in ("clothes", "swimwear", "boutique"):
        return "Loja de roupa"
    return "Outro"


def distancia_km(lat, lng):
    p1, p2 = math.radians(BASE_LAT), math.radians(lat)
    dp, dl = math.radians(lat - BASE_LAT), math.radians(lng - BASE_LNG)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(a))


def faixa(km):
    if km <= LIMITE_PRESENCIAL_KM:
        return "Presencial"
    if km <= LIMITE_LIGACAO_KM:
        return "Ligação"
    return "Mensagem"


def pegar_site(tags):
    return tags.get("website") or tags.get("contact:website") or tags.get("url") or ""


def pegar_redes(tags):
    redes = [tags.get(k) for k in ("contact:instagram", "contact:facebook")]
    return " | ".join(r for r in redes if r)


def pegar_telefone(tags):
    for k in ("phone", "contact:phone", "contact:mobile", "contact:whatsapp"):
        if tags.get(k):
            return tags[k].split(";")[0].strip()
    return ""


def pegar_email(tags):
    return tags.get("email") or tags.get("contact:email") or ""


def link_whatsapp(telefone):
    """Monta wa.me só para celular brasileiro."""
    d = "".join(c for c in telefone if c.isdigit())
    if len(d) == 11:
        d = "55" + d
    if len(d) == 13 and d.startswith("55") and d[4] == "9":
        return f"https://wa.me/{d}"
    return ""


def site_no_ar(url):
    """Só abre o endereço para ver se responde. Não copia nada da página."""
    if not url.startswith("http"):
        url = "http://" + url
    try:
        r = requests.head(url, headers=HEADERS, timeout=8, allow_redirects=True)
        if r.status_code in (403, 405):
            r = requests.get(url, headers=HEADERS, timeout=8, stream=True)
            r.close()
        return r.status_code < 400
    except requests.RequestException:
        return False


def situacao_site(site, redes):
    if not site:
        return "Só rede social" if redes else "Sem site"
    if any(dom in site.lower() for dom in SO_REDE_SOCIAL):
        return "Só rede social"
    if VERIFICAR_SITES and not site_no_ar(site):
        return "Site fora do ar"
    return "Tem site"


def numero(valor):
    try:
        return int(str(valor).split(";")[0].strip())
    except ValueError:
        return 0


def calcular_chance(tags, tipo, status, telefone, whatsapp, email, redes, abordagem):
    """Devolve (nota 0-100, lista de motivos)."""
    motivos = []

    # 1. Necessidade (até 40)
    necessidade = {"Sem site": 40, "Site fora do ar": 38,
                   "Só rede social": 32, "Tem site": 5}[status]
    motivos.append({
        "Sem site": "não tem site",
        "Site fora do ar": "site antigo fora do ar (já pagou por site antes)",
        "Só rede social": "depende só de rede social",
        "Tem site": "já tem site (só cabe reformulação)",
    }[status])

    # 2. Contato (até 20)
    contato = 0
    if whatsapp:
        contato += 12
        motivos.append("tem WhatsApp")
    elif telefone:
        contato += 6
        motivos.append("tem telefone")
    if email:
        contato += 4
    if redes:
        contato += 4
        motivos.append("ativo em rede social")
    contato = min(contato, 20)

    # 3. Estrutura do negócio (até 20)
    estrutura = 0
    if tags.get("opening_hours"):
        estrutura += 5
    if tags.get("addr:street"):
        estrutura += 4
    if any(k.startswith("payment:") and v == "yes" for k, v in tags.items()):
        estrutura += 3
    if tags.get("stars") or numero(tags.get("rooms")) or numero(tags.get("beds")):
        estrutura += 4
    if tags.get("cuisine") or tags.get("description"):
        estrutura += 2
    if tags.get("internet_access") or tags.get("air_conditioning"):
        estrutura += 2
    estrutura = min(estrutura, 20)
    if estrutura >= 12:
        motivos.append("negócio bem estruturado")

    # 4. Tipo (até 10)
    pts_tipo = PESO_TIPO.get(tipo, 3)
    if pts_tipo >= 9:
        motivos.append("depende de turista reservando online")

    # 5. Distância (até 10)
    pts_dist = {"Presencial": 10, "Ligação": 6, "Mensagem": 3}[abordagem]
    if abordagem == "Presencial":
        motivos.append("dá para visitar pessoalmente")

    nota = necessidade + contato + estrutura + pts_tipo + pts_dist

    # Penalidades
    if tags.get("brand") or tags.get("brand:wikidata") or tags.get("operator:wikidata"):
        nota -= 30
        motivos.append("rede/franquia: decisão fora do local")
    if not (telefone or email or redes):
        nota = min(nota, 15)
        motivos.append("sem contato público")

    return max(0, min(100, nota)), motivos


def calcular_preco(tags, tipo, status):
    """Devolve (oferta inicial, valor alvo, mínimo), arredondados de 50 em 50."""
    alvo = PRECO_BASE.get(tipo, 900)
    fator = 1.0

    if tags.get("tourism") == "hotel":
        fator += 0.15
    estrelas = numero(tags.get("stars"))
    if estrelas >= 3:
        fator += 0.10 * (estrelas - 2)
    if numero(tags.get("rooms")) >= 15 or numero(tags.get("beds")) >= 30:
        fator += 0.15
    if status == "Site fora do ar":
        fator += 0.10       # já pagou por site antes, entende o valor
    if status == "Tem site":
        fator -= 0.10       # reformulação costuma valer menos

    alvo = max(alvo * fator, PRECO_MINIMO_ABSOLUTO)

    def r50(v):
        return int(round(v / 50) * 50)

    return (r50(alvo * ANCORA), r50(alvo),
            r50(max(alvo * DESCONTO_MAXIMO, PRECO_MINIMO_ABSOLUTO)))


def descrever_sites(tags, tipo, status):
    """Devolve (texto do protótipo, texto do site final) para essa empresa."""
    base = SITES.get(tipo, SITES["Outro"])
    proto, final = base["prototipo"], base["final"]

    extras = []
    if status == "Site fora do ar":
        extras.append("mostrar como o site antigo voltaria, melhor e no celular")
    elif status == "Tem site":
        extras.append("reformulação: versão mais rápida e pensada para celular")
    elif status == "Só rede social":
        extras.append("usar as fotos e textos que já publicam (com permissão)")
    if numero(tags.get("stars")) >= 3 or tags.get("tourism") == "hotel":
        final += ", calendário de disponibilidade"
    if tags.get("opening_hours"):
        extras.append(f"horário: {tags['opening_hours']}")

    if extras:
        texto = "; ".join(extras)
        texto = texto[0].upper() + texto[1:]
        proto += ". " + texto
        final += ". " + texto
    return proto, final


def definir_entregas(lista):
    """Decide protótipo, site final ou nada. Os melhores ganham site final."""
    finais = 0
    for lead in lista:
        proto = lead.pop("_proto")
        final = lead.pop("_final")
        nota = lead["Chance de venda"]
        pode_final = (nota >= NOTA_SITE_FINAL
                      and lead["Abordagem"] != "Mensagem"
                      and lead["Site"] != "Tem site"
                      and finais < LIMITE_FINAIS)
        if pode_final:
            finais += 1
            lead["Preparar"] = "Site final"
            lead["Site final"] = final
            lead["Protótipo"] = ""
            lead["Horas estimadas"] = HORAS_FINAL
        elif nota >= NOTA_PROTOTIPO:
            lead["Preparar"] = "Protótipo"
            lead["Protótipo"] = proto
            lead["Site final"] = ""
            lead["Horas estimadas"] = HORAS_PROTOTIPO
        else:
            lead["Preparar"] = "Nada agora"
            lead["Protótipo"] = ""
            lead["Site final"] = ""
            lead["Horas estimadas"] = 0


def classificar(nota):
    if nota >= 70:
        return "Quente"
    if nota >= 50:
        return "Morno"
    return "Frio"


def main():
    leads = {}
    for cidade, (lat, lng) in CIDADES.items():
        print(f"Buscando em {cidade}...")
        elementos = consultar_overpass(montar_consulta(lat, lng))
        print(f"  {len(elementos)} lugares encontrados")
        for el in elementos:
            chave = f"{el['type']}/{el['id']}"
            if chave in leads:
                continue
            tags = el.get("tags", {})
            nome = tags.get("name", "").strip()
            if not nome:
                continue
            plat = el.get("lat") or el.get("center", {}).get("lat", lat)
            plng = el.get("lon") or el.get("center", {}).get("lon", lng)
            km = distancia_km(plat, plng)
            abordagem = faixa(km)
            tipo = identificar_tipo(tags)
            site, redes = pegar_site(tags), pegar_redes(tags)
            telefone, email = pegar_telefone(tags), pegar_email(tags)
            whatsapp = link_whatsapp(telefone)
            status = situacao_site(site, redes)
            nota, motivos = calcular_chance(tags, tipo, status, telefone,
                                            whatsapp, email, redes, abordagem)
            oferta, alvo, minimo = calcular_preco(tags, tipo, status)
            proto, final = descrever_sites(tags, tipo, status)
            leads[chave] = {
                "_proto": proto,
                "_final": final,
                "Chance de venda": nota,
                "Prioridade": classificar(nota),
                "Nome": nome,
                "Tipo": tipo,
                "Cidade": cidade,
                "Preparar": "",
                "Protótipo": "",
                "Site final": "",
                "Horas estimadas": 0,
                "Oferta inicial (R$)": oferta,
                "Valor alvo (R$)": alvo,
                "Mínimo (R$)": minimo,
                "Por quê": "; ".join(motivos),
                "Site": status,
                "URL atual": site,
                "Redes sociais": redes,
                "Telefone": telefone,
                "WhatsApp": whatsapp,
                "E-mail": email,
                "Distância (km)": round(km),
                "Abordagem": abordagem,
                "Ver no Google Maps": "https://www.google.com/maps/search/?api=1&query="
                                      + quote_plus(f"{nome} {cidade}"),
                "Nota Google (conferir)": "",
                "Status contato": "",
                "Valor fechado (R$)": "",
                "Observações": "",
            }
        time.sleep(3)  # respeita o servidor gratuito

    lista = sorted(leads.values(),
                   key=lambda x: (x["Chance de venda"], x["Valor alvo (R$)"]),
                   reverse=True)
    if not lista:
        sys.exit("Nenhum resultado. Verifique sua internet e tente de novo em alguns minutos.")
    definir_entregas(lista)

    wb = Workbook()
    ws = wb.active
    ws.title = "Leads"
    colunas = list(lista[0].keys())
    ws.append(colunas)
    for lead in lista:
        ws.append([lead[c] for c in colunas])

    for cel in ws[1]:
        cel.font = Font(bold=True, color="FFFFFF")
        cel.fill = PatternFill("solid", fgColor="1F2937")

    cores = {"Quente": "FECACA", "Morno": "FEF3C7", "Frio": "E5E7EB"}
    col_prio = colunas.index("Prioridade")
    for linha in ws.iter_rows(min_row=2):
        cel = linha[col_prio]
        cel.fill = PatternFill("solid", fgColor=cores[cel.value])
    cores_prep = {"Site final": "BBF7D0", "Protótipo": "BFDBFE", "Nada agora": "F3F4F6"}
    col_prep = colunas.index("Preparar")
    for linha in ws.iter_rows(min_row=2):
        cel = linha[col_prep]
        cel.fill = PatternFill("solid", fgColor=cores_prep[cel.value])
        cel.font = Font(bold=True)
    for nome_col in ("Protótipo", "Site final", "Por quê"):
        letra = get_column_letter(colunas.index(nome_col) + 1)
        for cel in ws[letra][1:]:
            cel.alignment = Alignment(wrap_text=True, vertical="top")
    for nome_col in ("Oferta inicial (R$)", "Valor alvo (R$)", "Mínimo (R$)", "Valor fechado (R$)"):
        letra = get_column_letter(colunas.index(nome_col) + 1)
        for cel in ws[letra][1:]:
            cel.number_format = '"R$" #,##0'

    larguras = {"Nome": 34, "Protótipo": 55, "Site final": 60, "Por quê": 60, "URL atual": 30, "Redes sociais": 30,
                "Ver no Google Maps": 30, "WhatsApp": 26, "Observações": 30}
    for i, c in enumerate(colunas, start=1):
        ws.column_dimensions[get_column_letter(i)].width = larguras.get(c, 15)
    ws.freeze_panes = "D2"
    ws.auto_filter.ref = ws.dimensions

    # Resumo
    resumo = wb.create_sheet("Resumo")
    resumo.append(["Prioridade", "Empresas", "Soma do valor alvo (R$)", "Valor alvo médio (R$)"])
    for p in ("Quente", "Morno", "Frio"):
        grupo = [l for l in lista if l["Prioridade"] == p]
        soma = sum(l["Valor alvo (R$)"] for l in grupo)
        resumo.append([p, len(grupo), soma, round(soma / len(grupo)) if grupo else 0])
    resumo.append([])
    resumo.append(["Abordagem", "Quentes", "Mornos"])
    for f in ("Presencial", "Ligação", "Mensagem"):
        resumo.append([f,
                       sum(1 for l in lista if l["Abordagem"] == f and l["Prioridade"] == "Quente"),
                       sum(1 for l in lista if l["Abordagem"] == f and l["Prioridade"] == "Morno")])
    resumo.append([])
    resumo.append(["Preparar", "Empresas", "Horas estimadas", "Soma do valor alvo (R$)"])
    for p in ("Site final", "Protótipo", "Nada agora"):
        grupo = [l for l in lista if l["Preparar"] == p]
        resumo.append([p, len(grupo), sum(l["Horas estimadas"] for l in grupo),
                       sum(l["Valor alvo (R$)"] for l in grupo)])
    for linha in (1, 6, 11):
        for cel in resumo[linha]:
            cel.font = Font(bold=True)
    for cel in list(resumo["D"])[11:14]:
        cel.number_format = '"R$" #,##0'
    for cel in list(resumo["C"])[1:4] + list(resumo["D"])[1:4]:
        cel.number_format = '"R$" #,##0'
    for col in "ABCD":
        resumo.column_dimensions[col].width = 24

    wb.save(ARQUIVO_SAIDA)
    quentes = sum(1 for l in lista if l["Prioridade"] == "Quente")
    print(f"\n{len(lista)} empresas salvas em {ARQUIVO_SAIDA} ({quentes} quentes).")


if __name__ == "__main__":
    main()
