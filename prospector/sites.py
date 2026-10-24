from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from tqdm import tqdm

from prospector.config import HEADERS
from prospector.modelos import Lead


def site_no_ar(url: str) -> bool:
    """Só abre o endereço para ver se responde. Não copia nada da página."""
    if not url or not str(url).strip():
        return False
    url = str(url).strip()
    if not url.startswith("http"):
        url = "http://" + url
    try:
        r = requests.head(url, headers=HEADERS, timeout=8, allow_redirects=True)
        if r.status_code in (403, 405):
            r = requests.get(url, headers=HEADERS, timeout=8, stream=True)
            r.close()
        return r.status_code < 400
    except (requests.RequestException, ValueError):
        return False


def verificar_sites(leads: list[Lead], workers: int = 16) -> int:
    """Verifica em paralelo os leads com status 'A verificar' e atualiza para 'Tem site' ou 'Site fora do ar'."""
    alvos = [
        lead for lead in (leads or [])
        if isinstance(lead, Lead) and lead.status_site == "A verificar"
    ]
    if not alvos:
        return 0

    max_workers = max(1, min(int(workers or 1), len(alvos)))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futuros = {pool.submit(site_no_ar, lead.site): lead for lead in alvos}
        for fut in tqdm(as_completed(futuros), total=len(futuros), desc="Verificando sites", leave=False):
            lead = futuros[fut]
            try:
                no_ar = bool(fut.result())
            except Exception:
                no_ar = False
            lead.status_site = "Tem site" if no_ar else "Site fora do ar"

    return len(alvos)
