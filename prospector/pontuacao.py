import math
from prospector.config import (
    ANCORA,
    BASE_LAT,
    BASE_LNG,
    DESCONTO_MAXIMO,
    HORAS_FINAL,
    HORAS_PROTOTIPO,
    LIMITE_FINAIS,
    LIMITE_LIGACAO_KM,
    LIMITE_PRESENCIAL_KM,
    NOTA_PROTOTIPO,
    NOTA_SITE_FINAL,
    PESO_TIPO,
    PRECO_BASE,
    PRECO_MINIMO_ABSOLUTO,
    SITES,
)


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
