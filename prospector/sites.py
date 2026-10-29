from concurrent.futures import ThreadPoolExecutor, as_completed
import socket
from urllib.parse import urlsplit

import requests
import urllib3
from tqdm import tqdm

from prospector.config import EMAIL_GRATUITO, HEADERS_SITE, SO_REDE_SOCIAL
from prospector.modelos import Lead

# Só queremos saber se o site abre; certificado vencido não significa site fora do ar.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_TIMEOUT = (5, 10)


def _dns_resolve(host: str) -> bool | None:
    """True se o nome existe, False se não existe, None se não deu para saber (falha temporária)."""
    try:
        socket.getaddrinfo(host, None)
        return True
    except socket.gaierror as e:
        return None if e.errno == socket.EAI_AGAIN else False
    except (UnicodeError, OSError):
        return False


def dominio_do_email(email: str | None) -> str:
    """Devolve o domínio próprio do e-mail (que provavelmente é o site), ou '' se for provedor gratuito."""
    texto = str(email or "").strip().lower()
    if texto.count("@") != 1:
        return ""
    dominio = texto.split("@")[1].strip()
    if "." not in dominio or dominio in EMAIL_GRATUITO or dominio.endswith(".gov.br"):
        return ""
    return dominio


def _variantes(url: str) -> tuple[list[str], list[str]]:
    """Endereços a tentar (https/http, com e sem www, e a raiz do domínio) e os hosts envolvidos."""
    partes = urlsplit(url if "://" in url else "http://" + url)
    host = (partes.hostname or "").lower()
    if not host:
        return [], []
    alternativo = host[4:] if host.startswith("www.") else "www." + host
    hosts = [host, alternativo]
    caminho = "" if partes.path in ("", "/") else partes.path
    if partes.query:
        caminho += "?" + partes.query
    esquemas = ["http", "https"] if partes.scheme == "http" else ["https", "http"]
    tentativas = [f"{e}://{h}{caminho}" for h in hosts for e in esquemas]
    if caminho:
        tentativas.append(f"https://{host}")
    return list(dict.fromkeys(tentativas)), hosts


def checar_site(url: str | None) -> str:
    """Devolve 'Tem site', 'Site fora do ar' ou 'Não confirmado'. Só abre o endereço, não copia nada.

    'Site fora do ar' só quando o domínio não existe ou recusa conexão em todas as variações;
    qualquer resposta do servidor (403, 404, 503...) ou lentidão fica como 'Não confirmado'.
    """
    if not url or not str(url).strip():
        return "Site fora do ar"
    tentativas, hosts = _variantes(str(url).strip())
    if not tentativas:
        return "Site fora do ar"

    dns = [_dns_resolve(h) for h in hosts]
    if all(d is False for d in dns):
        return "Site fora do ar"
    if not any(d is True for d in dns):
        return "Não confirmado"

    respondeu = False
    for alvo in tentativas:
        try:
            r = requests.get(alvo, headers=HEADERS_SITE, timeout=_TIMEOUT, stream=True,
                             verify=False, allow_redirects=True)
            r.close()
        except requests.Timeout:
            respondeu = True
            continue
        except (requests.RequestException, ValueError):
            continue
        if r.status_code < 400:
            return "Tem site"
        respondeu = True
    return "Não confirmado" if respondeu else "Site fora do ar"


def _dominio_a_descobrir(lead: Lead) -> str:
    """Domínio do e-mail do OSM quando o lead não tem site cadastrado (ex.: tags sem 'website')."""
    if lead.status_site not in ("Sem site", "Só rede social", "Não conferido") or lead.site:
        return ""
    tags = lead.tags if isinstance(lead.tags, dict) else {}
    return dominio_do_email(tags.get("email") or tags.get("contact:email"))


def verificar_sites(leads: list[Lead], workers: int = 16) -> int:
    """Verifica em paralelo os sites dos leads e atualiza o status.

    Leads 'A verificar' viram 'Tem site', 'Site fora do ar' ou 'Não confirmado'. Leads sem site
    cujo e-mail do OSM tem domínio próprio ganham o site se o domínio abrir.
    """
    alvos = []   # (lead, url, descoberto_pelo_email)
    for lead in leads or []:
        if not isinstance(lead, Lead):
            continue
        if lead.status_site == "A verificar":
            alvos.append((lead, lead.site, False))
            continue
        dominio = _dominio_a_descobrir(lead)
        if dominio:
            alvos.append((lead, "https://" + dominio, True))
    if not alvos:
        return 0

    max_workers = max(1, min(int(workers or 1), len(alvos)))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futuros = {pool.submit(checar_site, url): (lead, url, descoberto) for lead, url, descoberto in alvos}
        for fut in tqdm(as_completed(futuros), total=len(futuros), desc="Verificando sites", leave=False):
            lead, url, descoberto = futuros[fut]
            try:
                resultado = fut.result()
            except Exception:
                resultado = "Não confirmado"
            if descoberto:
                if resultado == "Tem site":
                    lead.site = url
                    lead.status_site = resultado
            else:
                lead.status_site = resultado

    return len(alvos)
