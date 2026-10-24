import dataclasses
from datetime import datetime, timedelta
import json
from pathlib import Path
import re
import requests

from prospector import config
from prospector.modelos import Municipio
from prospector.texto import normalizar_nome

URL_ESTADOS = "https://servicodados.ibge.gov.br/api/v1/localidades/estados"
URL_MUNICIPIOS = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf}/municipios"
URL_CENTROIDES = "https://servicodados.ibge.gov.br/api/v3/malhas/estados/{id_uf}/metadados?intrarregiao=municipio"
URL_POPULACAO = (
    "https://servicodados.ibge.gov.br/api/v3/agregados/6579/periodos/-1/"
    "variaveis/9324?localidades=N6[N3[{id_uf}]]"
)


def _expandir_ufs(ufs: list[str]) -> list[str]:
    """Expande 'todos' e valida cada sigla contra config.UFS."""
    if not ufs:
        return []
    resultado: list[str] = []
    for item in ufs:
        texto = str(item or "").strip()
        if texto.lower() == "todos":
            for sigla in config.UFS:
                if sigla not in resultado:
                    resultado.append(sigla)
            continue
        sigla = texto.upper()
        if sigla not in config.UFS:
            raise ValueError(f"UF desconhecida: {texto or sigla}")
        if sigla not in resultado:
            resultado.append(sigla)
    return resultado


def _ler_cache(caminho: Path) -> list[Municipio] | None:
    """Lê o arquivo de cache da UF se existir, for válido e estiver dentro do prazo."""
    if not caminho.is_file():
        return None
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        criado_em = datetime.fromisoformat(str(dados["criado_em"]))
        if datetime.now() - criado_em > timedelta(days=config.IBGE_CACHE_DIAS):
            return None
        itens = dados.get("municipios")
        if not isinstance(itens, list):
            return None
        return [
            Municipio(
                ibge=str(m["ibge"]),
                nome=str(m["nome"]),
                uf=str(m["uf"]),
                lat=float(m.get("lat") or 0.0),
                lng=float(m.get("lng") or 0.0),
                populacao=int(m.get("populacao") or 0),
            )
            for m in itens
            if isinstance(m, dict) and m.get("ibge") and m.get("nome") and m.get("uf")
        ]
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _salvar_cache(caminho: Path, municipios: list[Municipio]) -> None:
    """Grava a lista de municípios da UF em JSON UTF-8 com data de criação."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "criado_em": datetime.now().isoformat(timespec="seconds"),
        "municipios": [dataclasses.asdict(m) for m in municipios],
    }
    caminho.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _buscar_estados() -> dict[str, int]:
    """Obtém o mapa sigla -> id numérico dos estados na API do IBGE."""
    try:
        resp = requests.get(URL_ESTADOS, headers=config.HEADERS, timeout=60)
        resp.raise_for_status()
        dados = resp.json()
    except (requests.RequestException, ValueError):
        return {}
    if not isinstance(dados, list):
        return {}
    mapa: dict[str, int] = {}
    for item in dados:
        if isinstance(item, dict) and item.get("sigla") and item.get("id") is not None:
            try:
                mapa[str(item["sigla"]).upper()] = int(item["id"])
            except (ValueError, TypeError):
                continue
    return mapa


def _buscar_centroides(id_uf: int | None) -> dict[str, tuple[float, float]]:
    """Obtém (lat, lng) por código IBGE; falhas de rede devolvem dicionário vazio."""
    if not id_uf:
        return {}
    try:
        resp = requests.get(URL_CENTROIDES.format(id_uf=id_uf), headers=config.HEADERS, timeout=60)
        resp.raise_for_status()
        dados = resp.json()
    except (requests.RequestException, ValueError):
        return {}
    if not isinstance(dados, list):
        return {}
    centroides: dict[str, tuple[float, float]] = {}
    for item in dados:
        if not isinstance(item, dict):
            continue
        ibge = str(item.get("id") or "").strip()
        centro = item.get("centroide") or {}
        if not ibge or not isinstance(centro, dict):
            continue
        try:
            lat = float(centro["latitude"])
            lng = float(centro["longitude"])
            centroides[ibge] = (lat, lng)
        except (KeyError, TypeError, ValueError):
            continue
    return centroides


def _buscar_populacao(id_uf: int | None) -> dict[str, int]:
    """Obtém população estimada por código IBGE; falhas ou '-' viram 0."""
    if not id_uf:
        return {}
    try:
        resp = requests.get(URL_POPULACAO.format(id_uf=id_uf), headers=config.HEADERS, timeout=60)
        resp.raise_for_status()
        dados = resp.json()
    except (requests.RequestException, ValueError):
        return {}
    if not isinstance(dados, list):
        return {}
    populacoes: dict[str, int] = {}
    for item in dados:
        if not isinstance(item, dict):
            continue
        for res in item.get("resultados") or []:
            if not isinstance(res, dict):
                continue
            for s in res.get("series") or []:
                if not isinstance(s, dict):
                    continue
                loc = s.get("localidade") or {}
                serie = s.get("serie") or {}
                if not isinstance(loc, dict) or not isinstance(serie, dict):
                    continue
                ibge = str(loc.get("id") or "").strip()
                if not ibge or not serie:
                    continue
                ultimo_valor = str(list(serie.values())[-1]).strip()
                populacoes[ibge] = int(ultimo_valor) if ultimo_valor.isdigit() else 0
    return populacoes


def _baixar_uf(uf: str, ids_uf: dict[str, int]) -> list[Municipio]:
    """Baixa municípios, centroides e população de uma UF na API do IBGE."""
    try:
        resp = requests.get(URL_MUNICIPIOS.format(uf=uf), headers=config.HEADERS, timeout=60)
        resp.raise_for_status()
        dados_muns = resp.json()
        if not isinstance(dados_muns, list):
            raise ValueError("formato inesperado de municípios")
    except (requests.RequestException, ValueError) as exc:
        raise RuntimeError(f"Falha ao obter lista de municípios do IBGE para {uf}: {exc}") from exc

    id_uf = ids_uf.get(uf)
    if id_uf is None and dados_muns:
        primeiro_id = str((dados_muns[0] or {}).get("id") or "")
        if len(primeiro_id) >= 2 and primeiro_id[:2].isdigit():
            id_uf = int(primeiro_id[:2])

    centroides = _buscar_centroides(id_uf)
    populacoes = _buscar_populacao(id_uf)

    municipios: list[Municipio] = []
    for item in dados_muns:
        if not isinstance(item, dict) or item.get("id") is None or not item.get("nome"):
            continue
        ibge = str(item["id"]).strip()
        nome = str(item["nome"]).strip()
        lat, lng = centroides.get(ibge, (0.0, 0.0))
        pop = populacoes.get(ibge, 0)
        municipios.append(
            Municipio(ibge=ibge, nome=nome, uf=uf, lat=lat, lng=lng, populacao=pop)
        )
    return municipios


def listar_municipios(ufs: list[str], cache_dir: Path) -> list[Municipio]:
    """Lista municípios das UFs informadas usando cache local ou consultando o IBGE."""
    siglas = _expandir_ufs(ufs)
    cache_path = Path(cache_dir)
    resultado: list[Municipio] = []
    ids_uf: dict[str, int] | None = None

    for uf in siglas:
        arquivo = cache_path / f"{uf}.json"
        em_cache = _ler_cache(arquivo)
        if em_cache is not None:
            resultado.extend(em_cache)
            continue

        if ids_uf is None:
            ids_uf = _buscar_estados()

        muns_uf = _baixar_uf(uf, ids_uf)
        _salvar_cache(arquivo, muns_uf)
        resultado.extend(muns_uf)

    return resultado


def achar_cidade(texto: str, municipios: list[Municipio]) -> Municipio:
    """Localiza um município por 'Cidade/UF', 'Cidade - UF' ou 'Cidade UF'."""
    bruto = str(texto or "").strip()
    partes = [p for p in re.split(r"[/\-]+|\s+", bruto) if p]
    if len(partes) >= 2:
        uf_alvo = partes[-1].upper()
        nome_alvo = normalizar_nome(" ".join(partes[:-1]))
        for m in municipios or []:
            if m.uf.upper() == uf_alvo and normalizar_nome(m.nome) == nome_alvo:
                return m
    raise ValueError(f"Cidade não encontrada: {texto}")
