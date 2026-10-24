import csv
import dataclasses
from datetime import date
import io
from pathlib import Path
import re
import sqlite3
import zipfile
from rapidfuzz.fuzz import token_sort_ratio
import requests
from tqdm import tqdm

from prospector import config
from prospector.modelos import Estab, Lead, Municipio
from prospector.texto import link_whatsapp, normalizar_nome, normalizar_telefone, nucleo_nome

# Alguns campos da Receita podem ser muito longos; aumenta o limite do csv.reader com segurança
try:
    csv.field_size_limit(10 * 1024 * 1024)
except (OverflowError, ValueError):
    pass

_CNAES_KITESURF = {"8591100", "7721700"}
_TAMANHO_LOTE = 5000
_CHUNK_BYTES = 1024 * 1024


def mes_mais_recente() -> str:
    """Consulta o WebDAV da Receita via PROPFIND e devolve a maior pasta AAAA-MM disponível."""
    resp = requests.request(
        "PROPFIND",
        config.RECEITA_WEBDAV,
        auth=(config.RECEITA_TOKEN, ""),
        headers={"Depth": "1", **config.HEADERS},
        timeout=60,
    )
    resp.raise_for_status()
    meses = re.findall(r"/webdav/(\d{4}-\d{2})/", resp.text or "")
    if not meses:
        raise RuntimeError("Nenhuma pasta AAAA-MM encontrada no WebDAV da Receita.")
    return max(meses)


def _tamanho_remoto(url: str, auth: tuple[str, str]) -> int | None:
    """Obtém o Content-Length de um arquivo remoto via HEAD, ou None se indisponível."""
    try:
        resp = requests.head(url, auth=auth, headers=config.HEADERS, timeout=30, allow_redirects=True)
        if resp.status_code < 400:
            valor = resp.headers.get("Content-Length")
            if valor and str(valor).strip().isdigit():
                return int(str(valor).strip())
    except requests.RequestException:
        return None
    return None


def baixar(mes: str, destino: Path) -> list[Path]:
    """Baixa Municipios.zip e Estabelecimentos0..9.zip do mês informado em streaming."""
    pasta = Path(destino)
    pasta.mkdir(parents=True, exist_ok=True)
    nomes = ["Municipios.zip"] + [f"Estabelecimentos{i}.zip" for i in range(10)]
    auth = (config.RECEITA_TOKEN, "")
    base_url = config.RECEITA_WEBDAV.rstrip("/") + "/"
    arquivos: list[Path] = []

    for nome in nomes:
        url = f"{base_url}{mes}/{nome}"
        arq_final = pasta / nome
        arq_part = pasta / f"{nome}.part"

        if arq_final.is_file():
            tam_remoto = _tamanho_remoto(url, auth)
            if tam_remoto is not None and arq_final.stat().st_size == tam_remoto:
                arquivos.append(arq_final)
                continue

        with requests.get(
            url,
            auth=auth,
            headers=config.HEADERS,
            stream=True,
            timeout=(30, 300),
        ) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("Content-Length") or 0)
            with (
                open(arq_part, "wb") as f,
                tqdm(
                    total=total or None,
                    unit="B",
                    unit_scale=True,
                    desc=nome,
                    leave=False,
                ) as barra,
            ):
                for bloco in resp.iter_content(chunk_size=_CHUNK_BYTES):
                    if bloco:
                        f.write(bloco)
                        barra.update(len(bloco))

        arq_part.replace(arq_final)
        arquivos.append(arq_final)

    return arquivos


def mapa_municipios(caminho_zip: Path, municipios: list[Municipio]) -> dict[tuple[str, str], str]:
    """Mapeia (codigo_receita, uf) -> codigo_ibge casando o nome normalizado em cada UF."""
    por_nome: dict[str, list[tuple[str, str]]] = {}
    for m in municipios or []:
        if not m or not m.nome or not m.uf or not m.ibge:
            continue
        chave_nome = normalizar_nome(m.nome)
        if chave_nome:
            por_nome.setdefault(chave_nome, []).append((m.uf.upper(), str(m.ibge)))

    mapa: dict[tuple[str, str], str] = {}
    sem_par = 0

    caminho = Path(caminho_zip)
    if not caminho.is_file():
        return mapa

    with zipfile.ZipFile(caminho, "r") as zf:
        membros = zf.namelist()
        if not membros:
            return mapa
        with zf.open(membros[0], "r") as bin_f:
            texto_f = io.TextIOWrapper(bin_f, encoding="latin-1", errors="replace", newline="")
            leitor = csv.reader(texto_f, delimiter=";", quotechar='"')
            for linha in leitor:
                if not linha or len(linha) < 2:
                    continue
                cod_rf = str(linha[0] or "").strip()
                nome_rf = normalizar_nome(linha[1])
                if not cod_rf or not nome_rf:
                    continue
                pares = por_nome.get(nome_rf)
                if not pares:
                    sem_par += 1
                    continue
                for uf, ibge_cod in pares:
                    mapa[(cod_rf, uf)] = ibge_cod

    print(f"Municípios da Receita sem par no IBGE: {sem_par}")
    return mapa


def _formatar_data(bruto: str) -> str:
    """Converte data AAAAMMDD válida em AAAA-MM-DD, ou devolve string vazia."""
    s = str(bruto or "").strip()
    if len(s) != 8 or not s.isdigit():
        return ""
    try:
        dt = date(int(s[0:4]), int(s[4:6]), int(s[6:8]))
        return dt.isoformat()
    except ValueError:
        return ""


def linha_para_estab(campos: list[str], mapa: dict) -> Estab | None:
    """Converte uma linha de 30 colunas de Estabelecimentos num Estab filtrado ou None."""
    if not campos or len(campos) < 28 or not isinstance(mapa, dict):
        return None

    situacao = str(campos[5] or "").strip()
    if situacao != "02":
        return None

    cnae = str(campos[11] or "").strip()
    tipo = config.CNAE_TIPOS.get(cnae)
    if not tipo:
        return None

    nome = str(campos[4] or "").strip()
    if not nome:
        return None

    if cnae in _CNAES_KITESURF and not re.search(config.REGEX_KITESURF, nome, re.I):
        return None

    uf = str(campos[19] or "").strip().upper()
    cod_mun_rf = str(campos[20] or "").strip()
    municipio_ibge = mapa.get((cod_mun_rf, uf))
    if not municipio_ibge:
        return None

    cnpj = f"{str(campos[0] or '').strip()}{str(campos[1] or '').strip()}{str(campos[2] or '').strip()}"
    if not cnpj:
        return None

    partes_log = [str(campos[i] or "").strip() for i in (13, 14, 15)]
    logradouro = " ".join(p for p in partes_log if p)
    bairro = str(campos[17] or "").strip()
    cep = str(campos[18] or "").strip()

    telefone = normalizar_telefone(str(campos[22] or ""), str(campos[21] or ""))
    telefone2 = normalizar_telefone(str(campos[24] or ""), str(campos[23] or ""))
    email = str(campos[27] or "").strip().lower()
    abertura = _formatar_data(str(campos[10] or ""))

    return Estab(
        cnpj=cnpj,
        nome=nome,
        cnae=cnae,
        tipo=tipo,
        municipio_ibge=municipio_ibge,
        uf=uf,
        logradouro=logradouro,
        bairro=bairro,
        cep=cep,
        telefone=telefone,
        telefone2=telefone2,
        email=email,
        abertura=abertura,
    )


def _estab_para_tupla(e: Estab) -> tuple:
    """Converte um Estab na tupla de colunas da tabela SQLite."""
    return (
        e.cnpj,
        e.nome,
        e.cnae,
        e.tipo,
        e.municipio_ibge,
        e.uf,
        e.logradouro,
        e.bairro,
        e.cep,
        e.telefone,
        e.telefone2,
        e.email,
        e.abertura,
    )


def construir_base(zips: list[Path], caminho_db: Path, mapa: dict) -> int:
    """Lê os zips de estabelecimentos e reconstrói a tabela estab de forma atômica."""
    db_path = Path(caminho_db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    sql_insert = (
        "INSERT OR REPLACE INTO estab_novo "
        "(cnpj, nome, cnae, tipo, municipio_ibge, uf, logradouro, bairro, cep, "
        "telefone, telefone2, email, abertura) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )

    try:
        conn.execute("DROP TABLE IF EXISTS estab_novo")
        conn.execute(
            """
            CREATE TABLE estab_novo (
                cnpj TEXT PRIMARY KEY,
                nome TEXT,
                cnae TEXT,
                tipo TEXT,
                municipio_ibge TEXT,
                uf TEXT,
                logradouro TEXT,
                bairro TEXT,
                cep TEXT,
                telefone TEXT,
                telefone2 TEXT,
                email TEXT,
                abertura TEXT
            )
            """
        )
        conn.commit()

        lote: list[tuple] = []
        for caminho_zip in tqdm(list(zips or []), desc="Estabelecimentos", leave=False):
            arq = Path(caminho_zip)
            if not arq.is_file():
                continue
            with zipfile.ZipFile(arq, "r") as zf:
                membros = zf.namelist()
                if not membros:
                    continue
                with zf.open(membros[0], "r") as bin_f:
                    texto_f = io.TextIOWrapper(bin_f, encoding="latin-1", errors="replace", newline="")
                    leitor = csv.reader(texto_f, delimiter=";", quotechar='"')
                    for campos in leitor:
                        estab = linha_para_estab(campos, mapa)
                        if estab is None:
                            continue
                        lote.append(_estab_para_tupla(estab))
                        if len(lote) >= _TAMANHO_LOTE:
                            conn.executemany(sql_insert, lote)
                            conn.commit()
                            lote.clear()

        if lote:
            conn.executemany(sql_insert, lote)
            conn.commit()
            lote.clear()

        with conn:
            conn.execute("DROP TABLE IF EXISTS estab")
            conn.execute("ALTER TABLE estab_novo RENAME TO estab")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_estab_municipio ON estab(municipio_ibge)")

        total = conn.execute("SELECT COUNT(*) FROM estab").fetchone()[0]
        return int(total)
    finally:
        conn.close()


def estabs_do_municipio(caminho_db: Path, ibge: str) -> list[Estab]:
    """Devolve todos os estabelecimentos da Receita para o código IBGE informado."""
    db_path = Path(caminho_db)
    if not db_path.is_file() or not ibge:
        return []
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            """
            SELECT cnpj, nome, cnae, tipo, municipio_ibge, uf, logradouro,
                   bairro, cep, telefone, telefone2, email, abertura
            FROM estab
            WHERE municipio_ibge = ?
            """,
            (str(ibge),),
        )
        return [Estab(*linha) for linha in cur.fetchall()]
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def _pontuar_par(lead: Lead, nucleo_lead: str, estab: Estab, nucleo_estab: str) -> float:
    """Calcula a pontuação de casamento (0..100) entre um Lead OSM e um Estab da Receita."""
    tel_lead = str(lead.telefone or "").strip()
    if tel_lead and tel_lead in {str(estab.telefone or "").strip(), str(estab.telefone2 or "").strip()}:
        return 100.0
    if len(nucleo_lead) >= 4 and len(nucleo_estab) >= 4:
        return float(token_sort_ratio(nucleo_lead, nucleo_estab))
    return 0.0


def _enriquecer_lead(lead: Lead, estab: Estab) -> Lead:
    """Retorna cópia do Lead OSM enriquecida com contatos, CNPJ e abertura do Estab casado."""
    tel_estab = str(estab.telefone or estab.telefone2 or "").strip()
    telefone = str(lead.telefone or "").strip()
    whatsapp = str(lead.whatsapp or "").strip()
    if not telefone and tel_estab:
        telefone = tel_estab
        whatsapp = whatsapp or link_whatsapp(telefone)
    elif telefone and not whatsapp:
        whatsapp = link_whatsapp(telefone)

    email = str(lead.email or "").strip() or str(estab.email or "").strip()
    return dataclasses.replace(
        lead,
        fonte="OSM+Receita",
        telefone=telefone,
        whatsapp=whatsapp,
        email=email,
        cnpj=str(estab.cnpj or ""),
        abertura=str(estab.abertura or ""),
    )


def _estab_para_lead(estab: Estab, mun: Municipio) -> Lead:
    """Converte um Estab sem par no OSM num novo Lead de fonte 'Receita'."""
    tel = str(estab.telefone or estab.telefone2 or "").strip()
    logradouro = str(estab.logradouro or "").strip()
    tags = {"addr:street": logradouro} if logradouro else {}
    try:
        lat = float(mun.lat) if mun and mun.lat is not None else 0.0
        lng = float(mun.lng) if mun and mun.lng is not None else 0.0
    except (TypeError, ValueError):
        lat, lng = 0.0, 0.0

    return Lead(
        id=f"cnpj:{estab.cnpj}",
        fonte="Receita",
        nome=str(estab.nome or "").strip().title(),
        tipo=str(estab.tipo or "Outro"),
        municipio_ibge=str(mun.ibge if mun else estab.municipio_ibge or ""),
        cidade=str(mun.nome if mun else ""),
        uf=str(mun.uf if mun else estab.uf or ""),
        lat=lat,
        lng=lng,
        tags=tags,
        telefone=tel,
        whatsapp=link_whatsapp(tel),
        email=str(estab.email or "").strip(),
        cnpj=str(estab.cnpj or ""),
        abertura=str(estab.abertura or ""),
        status_site="Não conferido",
    )


def cruzar(leads: list[Lead], estabs: list[Estab], mun: Municipio) -> list[Lead]:
    """Cruza leads do OSM com estabelecimentos da Receita no município por atribuição gulosa."""
    lista_leads = list(leads or [])
    lista_estabs = list(estabs or [])
    if not lista_estabs:
        return list(lista_leads)

    nucleos_leads = [nucleo_nome(l.nome) for l in lista_leads]
    nucleos_estabs = [nucleo_nome(e.nome) for e in lista_estabs]

    pares: list[tuple[float, int, int]] = []
    for i, lead in enumerate(lista_leads):
        n_lead = nucleos_leads[i]
        for j, estab in enumerate(lista_estabs):
            pontos = _pontuar_par(lead, n_lead, estab, nucleos_estabs[j])
            if pontos >= 88.0:
                pares.append((pontos, i, j))

    pares.sort(key=lambda item: (-item[0], item[1], item[2]))

    casamento_lead: dict[int, int] = {}
    estabs_usados: set[int] = set()
    for _, i, j in pares:
        if i not in casamento_lead and j not in estabs_usados:
            casamento_lead[i] = j
            estabs_usados.add(j)

    resultado: list[Lead] = []
    for i, lead in enumerate(lista_leads):
        if i in casamento_lead:
            resultado.append(_enriquecer_lead(lead, lista_estabs[casamento_lead[i]]))
        else:
            resultado.append(lead)

    for j, estab in enumerate(lista_estabs):
        if j not in estabs_usados:
            resultado.append(_estab_para_lead(estab, mun))

    return resultado

