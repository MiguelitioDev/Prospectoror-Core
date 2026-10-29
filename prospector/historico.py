import json
import sqlite3
from pathlib import Path
from prospector.config import STATUS_BLOQUEIO
from prospector.modelos import Lead
from prospector.texto import normalizar_nome

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id TEXT PRIMARY KEY,
    nome_norm TEXT,
    uf TEXT,
    municipio_ibge TEXT,
    dados TEXT,
    primeira_vez TEXT,
    visto_em TEXT,
    exportado_em TEXT,
    rodada INTEGER,
    status_contato TEXT DEFAULT '',
    valor_fechado TEXT DEFAULT '',
    observacoes TEXT DEFAULT '',
    bloqueado INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS varreduras (
    municipio_ibge TEXT,
    fonte TEXT,
    varrido_em TEXT,
    PRIMARY KEY(municipio_ibge, fonte)
);
CREATE TABLE IF NOT EXISTS rodadas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    criada_em TEXT,
    arquivo TEXT,
    parametros TEXT
);
CREATE TABLE IF NOT EXISTS legado (
    nome_norm TEXT,
    uf TEXT,
    PRIMARY KEY(nome_norm, uf)
);
CREATE TABLE IF NOT EXISTS arquivos_importados (
    caminho TEXT PRIMARY KEY,
    importado_em TEXT
);
"""


def abrir(caminho: Path) -> sqlite3.Connection:
    """Abre (ou cria) o banco SQLite de histórico com WAL e tabelas garantidas."""
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(caminho)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_ESQUEMA)
    conn.commit()
    return conn


def _mesclar_lead(antigo: Lead, novo: Lead) -> Lead:
    """Combina um lead já salvo com uma nova leitura sem perder contatos nem verificação de site."""
    fontes = {antigo.fonte, novo.fonte}
    if "OSM+Receita" in fontes or ("OSM" in fontes and "Receita" in fontes):
        fonte = "OSM+Receita"
    else:
        fonte = novo.fonte or antigo.fonte

    if (
        novo.status_site == "A verificar"
        and novo.site == antigo.site
        and antigo.status_site in ("Tem site", "Site fora do ar", "Não confirmado")
    ):
        status_site = antigo.status_site
    elif novo.status_site == "Sem site" and not novo.site and antigo.status_site == "Tem site" and antigo.site:
        status_site = antigo.status_site   # site descoberto pelo e-mail; o OSM segue sem 'website'
    else:
        status_site = novo.status_site or antigo.status_site

    return Lead(
        id=novo.id,
        fonte=fonte,
        nome=novo.nome or antigo.nome,
        tipo=novo.tipo or antigo.tipo,
        municipio_ibge=novo.municipio_ibge or antigo.municipio_ibge,
        cidade=novo.cidade or antigo.cidade,
        uf=novo.uf or antigo.uf,
        lat=novo.lat if novo.lat is not None else antigo.lat,
        lng=novo.lng if novo.lng is not None else antigo.lng,
        tags=novo.tags if novo.tags else antigo.tags,
        site=novo.site or antigo.site,
        redes=novo.redes or antigo.redes,
        telefone=novo.telefone or antigo.telefone,
        whatsapp=novo.whatsapp or antigo.whatsapp,
        email=novo.email or antigo.email,
        cnpj=novo.cnpj or antigo.cnpj,
        abertura=novo.abertura or antigo.abertura,
        status_site=status_site,
    )


def salvar_leads(conn: sqlite3.Connection, leads: list[Lead], agora: str) -> int:
    """Insere leads novos ou atualiza existentes preservando histórico; devolve total de novos."""
    novos = 0
    for lead in leads or []:
        if not lead or not lead.id:
            continue
        row = conn.execute("SELECT dados FROM leads WHERE id = ?", (lead.id,)).fetchone()
        if row is None:
            nome_norm = normalizar_nome(lead.nome)
            dados_json = json.dumps(lead.para_dict(), ensure_ascii=False)
            conn.execute(
                """
                INSERT INTO leads (id, nome_norm, uf, municipio_ibge, dados, primeira_vez, visto_em)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (lead.id, nome_norm, lead.uf or "", lead.municipio_ibge or "", dados_json, agora, agora),
            )
            novos += 1
        else:
            try:
                antigo = Lead.de_dict(json.loads(row[0]))
                mesclado = _mesclar_lead(antigo, lead)
            except Exception:
                mesclado = lead
            nome_norm = normalizar_nome(mesclado.nome)
            dados_json = json.dumps(mesclado.para_dict(), ensure_ascii=False)
            conn.execute(
                """
                UPDATE leads
                SET nome_norm = ?, uf = ?, municipio_ibge = ?, dados = ?, visto_em = ?
                WHERE id = ?
                """,
                (nome_norm, mesclado.uf or "", mesclado.municipio_ibge or "", dados_json, agora, lead.id),
            )
    conn.commit()
    return novos


def marcar_varrido(conn: sqlite3.Connection, municipio_ibge: str, fonte: str, agora: str) -> None:
    """Registra o instante em que um município foi varrido por uma fonte."""
    conn.execute(
        """
        INSERT INTO varreduras (municipio_ibge, fonte, varrido_em)
        VALUES (?, ?, ?)
        ON CONFLICT(municipio_ibge, fonte) DO UPDATE SET varrido_em = excluded.varrido_em
        """,
        (str(municipio_ibge), str(fonte), str(agora)),
    )
    conn.commit()


def municipios_varridos(conn: sqlite3.Connection, fonte: str, desde: str) -> set[str]:
    """Devolve o conjunto de códigos IBGE varridos pela fonte a partir da data ISO informada."""
    rows = conn.execute(
        "SELECT municipio_ibge FROM varreduras WHERE fonte = ? AND varrido_em >= ?",
        (str(fonte), str(desde)),
    ).fetchall()
    return {r[0] for r in rows}


def pendentes(conn: sqlite3.Connection) -> list[Lead]:
    """Lista leads ainda não exportados, não bloqueados e fora do legado em ordem estável."""
    rows = conn.execute(
        """
        SELECT l.dados
        FROM leads l
        WHERE l.exportado_em IS NULL
          AND l.bloqueado = 0
          AND NOT EXISTS (
              SELECT 1 FROM legado g
              WHERE g.nome_norm = l.nome_norm AND g.uf = l.uf
          )
        ORDER BY l.primeira_vez, l.id
        """
    ).fetchall()
    resultado = []
    for (dados_txt,) in rows:
        try:
            d = json.loads(dados_txt)
            if not isinstance(d, dict):
                continue
            resultado.append(Lead.de_dict(d))
        except Exception:
            continue
    return resultado


def todos(conn: sqlite3.Connection) -> list[Lead]:
    """Lista todos os leads do banco, exportados ou não."""
    resultado = []
    for (dados_txt,) in conn.execute("SELECT dados FROM leads ORDER BY id").fetchall():
        try:
            d = json.loads(dados_txt)
            if isinstance(d, dict):
                resultado.append(Lead.de_dict(d))
        except Exception:
            continue
    return resultado


def nova_rodada(conn: sqlite3.Connection, arquivo: str, parametros: dict, agora: str) -> int:
    """Cria um registro de rodada de exportação e devolve seu ID."""
    cur = conn.execute(
        "INSERT INTO rodadas (criada_em, arquivo, parametros) VALUES (?, ?, ?)",
        (str(agora), str(arquivo), json.dumps(parametros or {}, ensure_ascii=False)),
    )
    conn.commit()
    return int(cur.lastrowid)


def marcar_exportados(conn: sqlite3.Connection, ids: list[str], rodada: int, agora: str) -> None:
    """Marca os leads informados como exportados na rodada."""
    for lead_id in ids or []:
        conn.execute(
            "UPDATE leads SET exportado_em = ?, rodada = ? WHERE id = ?",
            (str(agora), int(rodada), str(lead_id)),
        )
    conn.commit()


def _formatar_valor_planilha(valor, eh_valor_fechado: bool = False) -> str:
    """Converte célula lida da planilha em texto limpo."""
    if valor is None:
        return ""
    if eh_valor_fechado and isinstance(valor, (int, float)) and not isinstance(valor, bool):
        if isinstance(valor, float) and valor.is_integer():
            return str(int(valor))
        return str(valor)
    texto = str(valor).strip()
    if eh_valor_fechado and texto.endswith(".0") and texto[:-2].lstrip("-").isdigit():
        return texto[:-2]
    return texto


def atualizar_status(conn: sqlite3.Connection, linhas: list[dict]) -> int:
    """Sincroniza status, valor fechado e observações vindos da planilha; devolve nº de leads atualizados."""
    atualizados = 0
    mapa_colunas = {
        "Status contato": ("status_contato", False),
        "Valor fechado (R$)": ("valor_fechado", True),
        "Observações": ("observacoes", False),
    }
    for linha in linhas or []:
        if not isinstance(linha, dict):
            continue
        lead_id = linha.get("ID")
        if lead_id is None or str(lead_id).strip() == "":
            continue
        lead_id = str(lead_id).strip()

        row = conn.execute("SELECT bloqueado FROM leads WHERE id = ?", (lead_id,)).fetchone()
        if row is None:
            continue

        bloqueado_atual = int(row[0] or 0)
        campos_sql = []
        valores = []
        for chave_planilha, (coluna_db, eh_valor) in mapa_colunas.items():
            if chave_planilha in linha:
                txt = _formatar_valor_planilha(linha[chave_planilha], eh_valor_fechado=eh_valor)
                campos_sql.append(f"{coluna_db} = ?")
                valores.append(txt)
                if chave_planilha == "Status contato" and txt in STATUS_BLOQUEIO:
                    bloqueado_atual = 1

        if not campos_sql:
            continue

        campos_sql.append("bloqueado = ?")
        valores.append(bloqueado_atual)
        valores.append(lead_id)
        conn.execute(f"UPDATE leads SET {', '.join(campos_sql)} WHERE id = ?", valores)
        atualizados += 1

    conn.commit()
    return atualizados


def importar_legado(conn: sqlite3.Connection, linhas: list[dict]) -> int:
    """Importa leads com contato de planilhas antigas para a tabela legado; devolve quantos novos entraram."""
    inseridos = 0
    canais = ("Telefone", "E-mail", "WhatsApp", "Redes sociais")
    for linha in linhas or []:
        if not isinstance(linha, dict):
            continue
        nome_norm = normalizar_nome(linha.get("Nome") or "")
        if not nome_norm:
            continue
        if not any(str(linha.get(c) or "").strip() for c in canais):
            continue
        cidade_raw = str(linha.get("Cidade") or "")
        if " - " in cidade_raw:
            uf = cidade_raw.rsplit(" - ", 1)[1].strip().upper()
        else:
            uf = ""
        cur = conn.execute(
            "INSERT OR IGNORE INTO legado (nome_norm, uf) VALUES (?, ?)",
            (nome_norm, uf),
        )
        if cur.rowcount > 0:
            inseridos += 1
    conn.commit()
    return inseridos
