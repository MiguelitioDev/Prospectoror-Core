import re
import time
import requests

from prospector.config import HEADERS, ORGAO_PUBLICO, SERVIDORES, SO_REDE_SOCIAL, TIPOS
from prospector.modelos import Lead, Municipio
from prospector.texto import link_whatsapp, normalizar_telefone


def montar_consulta_area(ibge: str, tipos: dict[str, list[str]]) -> str:
    """Monta a consulta Overpass para buscar estabelecimentos na área oficial do município."""
    partes = []
    for filtros in (tipos or {}).values():
        for filtro in filtros or []:
            partes.append(f'nwr[{filtro}]["name"](area.a);')
    codigo = str(ibge or "").strip()
    return (
        f'[out:json][timeout:180];area["IBGE:GEOCODIGO"="{codigo}"]["admin_level"="8"]->.a;'
        f"({''.join(partes)});out center tags;"
    )


def consultar_overpass(consulta: str) -> list[dict] | None:
    """Executa a consulta rotacionando servidores Overpass; devolve None se todos falharem."""
    for url in SERVIDORES:
        for tentativa in range(2):
            try:
                r = requests.post(url, data={"data": consulta},
                                  headers=HEADERS, timeout=200)
                if r.status_code == 429:
                    print(f"  ! {url} respondeu 429, aguardando 30s...")
                    time.sleep(30)
                    break
                if r.status_code == 200:
                    dados = r.json()
                    if not isinstance(dados, dict):
                        raise ValueError("resposta JSON não é um objeto")
                    remark = str(dados.get("remark") or "").lower()
                    if "runtime error" in remark or "timed out" in remark:
                        print(f"  ! {url} retornou erro/timeout no remark: {dados.get('remark')}")
                    else:
                        elementos = dados.get("elements", [])
                        return elementos if isinstance(elementos, list) else []
                else:
                    print(f"  ! {url} respondeu {r.status_code}, tentando de novo...")
            except (requests.RequestException, ValueError) as e:
                print(f"  ! Falha em {url}: {e}")
            time.sleep(5 * (tentativa + 1))
    return None


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


def pegar_site(tags):
    return tags.get("website") or tags.get("contact:website") or tags.get("url") or ""


def pegar_redes(tags):
    redes = [tags.get(k) for k in ("contact:instagram", "contact:facebook")]
    return " | ".join(r for r in redes if r)


def pegar_telefone(tags: dict) -> str:
    """Extrai e normaliza o primeiro telefone válido das tags do OSM."""
    for k in ("phone", "contact:phone", "contact:mobile", "contact:whatsapp"):
        if tags.get(k):
            return normalizar_telefone(str(tags[k]))
    return ""


def pegar_email(tags):
    return tags.get("email") or tags.get("contact:email") or ""


def _status_site_inicial(site: str, redes: str) -> str:
    """Define o status inicial do site antes da verificação HTTP em lote."""
    if not site:
        return "Só rede social" if redes else "Sem site"
    if any(dom in site.lower() for dom in SO_REDE_SOCIAL):
        return "Só rede social"
    return "A verificar"


def _extrair_coordenadas(el: dict, mun: Municipio) -> tuple[float, float]:
    """Obtém (lat, lng) do elemento OSM ou de seu center, caindo para o centroide do município."""
    centro = el.get("center") if isinstance(el.get("center"), dict) else {}
    lat_bruto = el.get("lat") if el.get("lat") is not None else centro.get("lat")
    lng_bruto = el.get("lon") if el.get("lon") is not None else centro.get("lon")

    try:
        lat = float(lat_bruto) if lat_bruto is not None else float(mun.lat)
    except (TypeError, ValueError):
        lat = float(mun.lat)

    try:
        lng = float(lng_bruto) if lng_bruto is not None else float(mun.lng)
    except (TypeError, ValueError):
        lng = float(mun.lng)

    return lat, lng


def elemento_para_lead(el: dict, mun: Municipio) -> Lead | None:
    """Converte um elemento do Overpass em Lead, ou None se não for um estabelecimento válido."""
    if not isinstance(el, dict) or not isinstance(mun, Municipio):
        return None
    tipo_osm = str(el.get("type") or "").strip()
    id_osm = el.get("id")
    if not tipo_osm or id_osm is None:
        return None

    tags_brutas = el.get("tags")
    tags = dict(tags_brutas) if isinstance(tags_brutas, dict) else {}
    nome = str(tags.get("name") or "").strip()
    if not nome:
        return None

    if tags.get("tourism") == "information":
        operador = str(tags.get("operator") or "")
        if re.search(ORGAO_PUBLICO, f"{nome} {operador}", flags=re.IGNORECASE):
            return None

    lat, lng = _extrair_coordenadas(el, mun)
    tipo = identificar_tipo(tags)
    site = str(pegar_site(tags) or "").strip()
    redes = str(pegar_redes(tags) or "").strip()
    telefone = pegar_telefone(tags)
    whatsapp = link_whatsapp(telefone)
    email = str(pegar_email(tags) or "").strip()
    status_site = _status_site_inicial(site, redes)

    return Lead(
        id=f"osm:{tipo_osm}/{id_osm}",
        fonte="OSM",
        nome=nome,
        tipo=tipo,
        municipio_ibge=str(mun.ibge),
        cidade=str(mun.nome),
        uf=str(mun.uf),
        lat=lat,
        lng=lng,
        tags=tags,
        site=site,
        redes=redes,
        telefone=telefone,
        whatsapp=whatsapp,
        email=email,
        status_site=status_site,
    )


def buscar_municipio(mun: Municipio, tipos: dict | None = None) -> list[Lead] | None:
    """Busca todos os estabelecimentos do município no Overpass e devolve a lista de Leads."""
    tipos_busca = TIPOS if tipos is None else tipos
    consulta = montar_consulta_area(mun.ibge, tipos_busca)
    elementos = consultar_overpass(consulta)
    if elementos is None:
        return None

    leads: list[Lead] = []
    vistos: set[str] = set()
    for el in elementos:
        lead = elemento_para_lead(el, mun)
        if lead is None or lead.id in vistos:
            continue
        vistos.add(lead.id)
        leads.append(lead)
    return leads
