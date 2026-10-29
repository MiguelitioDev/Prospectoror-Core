import argparse
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
import re
import sqlite3
import sys
import time
import requests
from tqdm import tqdm

from prospector import cnpj, config, historico, ibge, osm, planilha, pontuacao, sites
from prospector.modelos import Municipio
from prospector.planilha import gerar_planilha

_COMANDOS = ("buscar", "sincronizar", "cnpj", "reverificar")


def _criar_parser() -> argparse.ArgumentParser:
    """Cria o parser de linha de comando com os subcomandos buscar, sincronizar e cnpj."""
    parser = argparse.ArgumentParser(
        prog="buscar_leads.py",
        description="Prospector de leads em escala nacional (OSM + Receita).",
    )
    parser.add_argument("--dados", default=None, help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="comando")

    p_buscar = sub.add_parser("buscar", help="Busca leads nos municípios e gera planilha.")
    p_buscar.add_argument("--uf", nargs="+", default=None, help="Siglas de UF (ex.: CE RN) ou 'todos'.")
    p_buscar.add_argument("--cidade", nargs="+", default=None, help="Cidades específicas (ex.: 'Gramado/RS').")
    p_buscar.add_argument("--min-pop", type=int, default=0, help="População mínima do município.")
    p_buscar.add_argument("--max-municipios", type=int, default=None, help="Máximo de municípios varridos na rodada.")
    p_buscar.add_argument("--revarrer-dias", type=int, default=None, help="Pular municípios varridos há menos de N dias.")
    p_buscar.add_argument(
        "--ordem",
        choices=("populacao", "distancia"),
        default="populacao",
        help="Critério de ordenação dos municípios.",
    )
    p_buscar.add_argument("--limite", type=int, default=None, help="Máximo de leads na aba Abordar.")
    p_buscar.add_argument(
        "--incluir-sem-contato",
        action="store_true",
        help="Exporta também leads sem contato na aba 'Pesquisar contato'.",
    )
    p_buscar.add_argument(
        "--sem-verificar-sites",
        action="store_true",
        help="Não testa se os sites estão no ar durante a rodada.",
    )
    p_buscar.add_argument("--tipos", nargs="+", default=None, help="Filtra tipos de negócio.")
    p_buscar.add_argument("--saida", default=None, help="Pasta onde ler/salvar planilhas.")
    p_buscar.add_argument("--dados", default=None, help=argparse.SUPPRESS)

    p_sinc = sub.add_parser("sincronizar", help="Lê planilhas da pasta e atualiza status no banco.")
    p_sinc.add_argument("--saida", default=None, help="Pasta onde estão as planilhas.")
    p_sinc.add_argument("--dados", default=None, help=argparse.SUPPRESS)

    p_rev = sub.add_parser(
        "reverificar",
        help="Confere de novo os sites marcados 'fora do ar' e procura o site pelo e-mail de quem está 'Sem site'.",
    )
    p_rev.add_argument("--dados", default=None, help=argparse.SUPPRESS)

    p_cnpj = sub.add_parser("cnpj", help="Baixa e constrói a base local de CNPJ da Receita.")
    p_cnpj.add_argument("--mes", default=None, help="Mês AAAA-MM da Receita (padrão: mais recente).")
    p_cnpj.add_argument("--manter-zips", action="store_true", help="Não apaga os arquivos .zip após importar.")
    p_cnpj.add_argument("--dados", default=None, help=argparse.SUPPRESS)

    return parser


def _normalizar_argv(argv: list[str] | None) -> list[str]:
    """Insere o subcomando 'buscar' quando nenhum subcomando explícito foi informado."""
    lista = list(sys.argv[1:] if argv is None else argv)
    if not lista:
        return ["buscar"]
    if lista[0] in ("-h", "--help"):
        return lista
    # Se algum token antes de flags de valor for subcomando conhecido, mantém; se começar com '-', prefixa buscar
    if lista[0] not in _COMANDOS:
        # Caso --dados PASTA venha antes do subcomando
        if lista[0] == "--dados" and len(lista) >= 3 and lista[2] in _COMANDOS:
            return [lista[2], "--dados", lista[1], *lista[3:]]
        return ["buscar", *lista]
    return lista


def _sincronizar_planilhas(conn: sqlite3.Connection, pasta_saida: Path, agora_iso: str) -> None:
    """Lê planilhas leads_*.xlsx da pasta de saída, sincronizando status ou importando legado."""
    if not pasta_saida.exists():
        return
    importados = {
        r[0] for r in conn.execute("SELECT caminho FROM arquivos_importados").fetchall()
    }
    for arq in sorted(pasta_saida.glob("leads_*.xlsx")):
        chave_arq = str(arq.resolve())
        if chave_arq in importados or arq.name in importados:
            continue
        try:
            linhas = planilha.ler_status(arq)
            historico.atualizar_status(conn, linhas)
        except ValueError as e:
            if "formato antigo" in str(e):
                try:
                    linhas_leg = planilha.ler_legado(arq)
                    historico.importar_legado(conn, linhas_leg)
                    conn.execute(
                        "INSERT OR IGNORE INTO arquivos_importados (caminho, importado_em) VALUES (?, ?)",
                        (chave_arq, agora_iso),
                    )
                    conn.commit()
                except Exception as erro_leg:
                    print(f"  ! Não consegui ler {arq.name}: {erro_leg}")
            else:
                print(f"  ! Não consegui ler {arq.name}: {e}")
        except Exception as e:
            print(f"  ! Não consegui ler {arq.name}: {e}")


def _extrair_ufs_de_cidades(cidades: list[str]) -> list[str]:
    """Extrai a lista única de siglas de UF citadas nas strings de --cidade."""
    ufs: list[str] = []
    for texto in cidades or []:
        partes = [p for p in re.split(r"[/\-]+|\s+", str(texto or "").strip()) if p]
        if len(partes) >= 2:
            uf = partes[-1].upper()
            if uf not in ufs:
                ufs.append(uf)
    return ufs


def _selecionar_municipios(
    conn: sqlite3.Connection,
    args: argparse.Namespace,
    pasta_dados: Path,
    agora: datetime,
) -> tuple[list[Municipio], int]:
    """Resolve, filtra, ordena e fatia a lista de municípios da rodada; devolve (a_varrer, faltam)."""
    cache_ibge = pasta_dados / "ibge"
    if args.cidade:
        ufs_cidades = _extrair_ufs_de_cidades(args.cidade)
        if not ufs_cidades:
            raise ValueError(f"Cidade não encontrada: {args.cidade[0]}")
        base_muns = ibge.listar_municipios(ufs_cidades, cache_ibge)
        muns = [ibge.achar_cidade(c, base_muns) for c in args.cidade]
    else:
        ufs = args.uf if args.uf else list(config.UFS_PADRAO)
        muns = ibge.listar_municipios(ufs, cache_ibge)

    min_pop = int(args.min_pop or 0)
    if min_pop > 0:
        muns = [m for m in muns if (m.populacao or 0) >= min_pop]

    if args.ordem == "distancia":
        muns.sort(key=lambda m: pontuacao.distancia_km(m.lat, m.lng))
    else:
        muns.sort(key=lambda m: -(m.populacao or 0))

    revarrer = config.REVARRER_DIAS if args.revarrer_dias is None else int(args.revarrer_dias)
    if revarrer > 0:
        desde = (agora - timedelta(days=revarrer)).isoformat(timespec="seconds")
        ja_varridos = historico.municipios_varridos(conn, "osm", desde)
        muns = [m for m in muns if m.ibge not in ja_varridos]

    max_muns = config.MAX_MUNICIPIOS if args.max_municipios is None else int(args.max_municipios)
    max_muns = max(0, max_muns)
    escolhidos = muns[:max_muns]
    faltam = max(0, len(muns) - len(escolhidos))
    return escolhidos, faltam


def _proximo_caminho_saida(pasta_saida: Path, agora: datetime) -> Path:
    """Devolve um caminho leads_AAAA-MM-DD_HHMMSS.xlsx que ainda não exista na pasta."""
    base = f"leads_{agora:%Y-%m-%d_%H%M%S}"
    caminho = pasta_saida / f"{base}.xlsx"
    if not caminho.exists():
        return caminho
    i = 2
    while True:
        cand = pasta_saida / f"{base}_{i}.xlsx"
        if not cand.exists():
            return cand
        i += 1


def _executar_buscar(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    argv_usado: list[str],
    pasta_dados: Path,
    pasta_saida: Path,
) -> int:
    """Executa o fluxo completo do subcomando 'buscar' (passos 1 a 8)."""
    if args.tipos:
        invalidos = [t for t in args.tipos if t not in config.TIPOS]
        if invalidos:
            validos = ", ".join(config.TIPOS.keys())
            parser.error(f"Tipo desconhecido: {', '.join(invalidos)}. Válidos: {validos}")
        tipos_osm = {t: config.TIPOS[t] for t in args.tipos}
        tipos_filtro = set(args.tipos)
    else:
        tipos_osm = config.TIPOS
        tipos_filtro = None

    agora = datetime.now()
    agora_iso = agora.isoformat(timespec="seconds")
    conn = historico.abrir(pasta_dados / "prospector.db")
    try:
        # Passo 1: Sincronizar planilhas existentes na pasta de saída
        _sincronizar_planilhas(conn, pasta_saida, agora_iso)

        # Passo 2: Municípios a varrer
        try:
            a_varrer, faltam_inicial = _selecionar_municipios(conn, args, pasta_dados, agora)
        except ValueError as e:
            parser.error(str(e))
            return 2

        # Passo 3: Varredura Overpass por município
        varridos = 0
        falharam = 0
        novos_total = 0
        try:
            for idx, mun in enumerate(tqdm(a_varrer, desc="Municípios", leave=False)):
                try:
                    leads_mun = osm.buscar_municipio(mun, tipos_osm)
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    print(f"  ! Erro inesperado em {mun.nome}/{mun.uf}: {e}")
                    falharam += 1
                    continue

                if leads_mun is None:
                    print(f"  ! Falha ao consultar {mun.nome}/{mun.uf}; ficará para a próxima rodada.")
                    falharam += 1
                    continue

                caminho_cnpj = pasta_dados / "cnpj.db"
                if caminho_cnpj.exists():
                    try:
                        estabs = cnpj.estabs_do_municipio(caminho_cnpj, mun.ibge)
                        leads_mun = cnpj.cruzar(leads_mun, estabs, mun)
                    except Exception as e:
                        print(f"  ! Erro ao ler base CNPJ em {mun.nome}/{mun.uf}: {e}")

                instante = datetime.now().isoformat(timespec="seconds")
                novos_total += historico.salvar_leads(conn, leads_mun, instante)
                historico.marcar_varrido(conn, mun.ibge, "osm", instante)
                varridos += 1
                if idx < len(a_varrer) - 1:
                    time.sleep(2)
        except KeyboardInterrupt:
            print("Interrompido. O que já foi varrido está salvo.")

        nao_processados = max(0, len(a_varrer) - varridos - falharam)
        faltam = faltam_inicial + falharam + nao_processados

        # Passo 4: Pendentes e verificação de sites em paralelo
        pend = historico.pendentes(conn)
        if tipos_filtro is not None:
            pend = [l for l in pend if l.tipo in tipos_filtro]

        if not args.sem_verificar_sites and pend:
            verificados = sites.verificar_sites(pend)
            if verificados:
                historico.salvar_leads(conn, pend, datetime.now().isoformat(timespec="seconds"))

        # Passo 5: Pontuação, ordenação e separação em Abordar / Pesquisar contato
        linhas = [pontuacao.pontuar(l) for l in pend]
        linhas.sort(key=lambda r: (r["Chance de venda"], r["Valor alvo (R$)"]), reverse=True)

        mapa_contato = {l.id: l.tem_contato() for l in pend}
        com_contato = [r for r in linhas if mapa_contato.get(r["ID"], False)]
        sem_contato = [r for r in linhas if not mapa_contato.get(r["ID"], False)]

        limite = config.LIMITE_EXPORTAR if args.limite is None else max(0, int(args.limite))
        abordar = com_contato[:limite]
        pontuacao.definir_entregas(abordar)

        if args.incluir_sem_contato:
            pesquisar = sem_contato[: config.LIMITE_SEM_CONTATO]
        else:
            pesquisar = []

        # Passo 6: Nada a exportar
        if not abordar and not pesquisar:
            print("Nenhum lead novo para exportar.")
            return 0

        # Passo 7: Registrar rodada, salvar planilha e só depois marcar exportados
        ids_exportados = [r["ID"] for r in abordar] + [r["ID"] for r in pesquisar]
        fila_restante = max(0, len(pend) - len(ids_exportados))

        caminho_alvo = _proximo_caminho_saida(pasta_saida, datetime.now())
        info_rodada = {
            "Data": agora_iso,
            "Comando": " ".join(argv_usado),
            "Municípios varridos": varridos,
            "Falharam": falharam,
            "Faltam varrer": faltam,
            "Leads novos": novos_total,
            "Exportados (Abordar)": len(abordar),
            "Exportados (Pesquisar contato)": len(pesquisar),
            "Fila restante": fila_restante,
        }

        rodada_id = historico.nova_rodada(conn, caminho_alvo.name, info_rodada, agora_iso)
        caminho_salvo = gerar_planilha(abordar, pesquisar, info_rodada, caminho_alvo)
        historico.marcar_exportados(conn, ids_exportados, rodada_id, datetime.now().isoformat(timespec="seconds"))

        # Passo 8: Resumo no terminal
        print(
            f"Municípios varridos: {varridos} | Falharam: {falharam} | Faltam: {faltam}\n"
            f"Leads novos: {novos_total} | Exportados: {len(ids_exportados)} | Fila restante: {fila_restante}\n"
            f"Planilha salva em: {caminho_salvo}"
        )
        return 0
    finally:
        conn.close()


def _executar_cnpj(args: argparse.Namespace, pasta_dados: Path) -> int:
    """Baixa os arquivos da Receita e reconstrói o banco local dados/cnpj.db."""
    print("Vai baixar ~5,5 GB e levar de 30 a 90 minutos.")
    try:
        mes = str(args.mes).strip() if getattr(args, "mes", None) else cnpj.mes_mais_recente()
        muns = ibge.listar_municipios(["todos"], pasta_dados / "ibge")
        pasta_zips = pasta_dados / "receita" / mes
        arquivos = cnpj.baixar(mes, pasta_zips)
    except (requests.RequestException, RuntimeError) as e:
        print(f"Erro ao baixar dados da Receita/IBGE: {e}")
        return 1

    zip_muns = next((p for p in arquivos if p.name.lower() == "municipios.zip"), pasta_zips / "Municipios.zip")
    zips_estabs = [p for p in arquivos if p.name.lower() != "municipios.zip"]

    mapa = cnpj.mapa_municipios(zip_muns, muns)
    total = cnpj.construir_base(zips_estabs, pasta_dados / "cnpj.db", mapa)

    if not getattr(args, "manter_zips", False):
        for arq in arquivos:
            try:
                Path(arq).unlink(missing_ok=True)
            except OSError:
                pass
        try:
            pasta_zips.rmdir()
        except OSError:
            pass

    print(f"Base CNPJ pronta: {total} estabelecimentos gravados.")
    return 0


def _executar_reverificar(pasta_dados: Path) -> int:
    """Refaz a checagem de sites de todo o banco e grava só o que mudou."""
    conn = historico.abrir(pasta_dados / "prospector.db")
    try:
        leads = historico.todos(conn)
        antes = {l.id: (l.status_site, l.site) for l in leads}
        for lead in leads:
            if lead.status_site == "Site fora do ar" and lead.site:
                lead.status_site = "A verificar"
        sites.verificar_sites(leads)

        mudaram = [l for l in leads if (l.status_site, l.site) != antes[l.id]]
        historico.salvar_leads(conn, mudaram, datetime.now().isoformat(timespec="seconds"))
    finally:
        conn.close()

    novos = Counter(l.status_site for l in mudaram)
    detalhe = ", ".join(f"{n} {s}" for s, n in sorted(novos.items())) or "nenhuma mudança"
    print(f"Reverificação concluída: {len(mudaram)} leads atualizados ({detalhe}).")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Ponto de entrada da CLI do Prospector."""
    parser = _criar_parser()
    argv_norm = _normalizar_argv(argv)
    args = parser.parse_args(argv_norm)

    comando = args.comando or "buscar"
    pasta_dados = Path(args.dados if getattr(args, "dados", None) else config.PASTA_DADOS)
    pasta_saida = Path(getattr(args, "saida", None) or config.PASTA_SAIDA)

    if comando == "cnpj":
        return _executar_cnpj(args, pasta_dados)

    if comando == "reverificar":
        return _executar_reverificar(pasta_dados)

    if comando == "sincronizar":
        agora_iso = datetime.now().isoformat(timespec="seconds")
        conn = historico.abrir(pasta_dados / "prospector.db")
        try:
            _sincronizar_planilhas(conn, pasta_saida, agora_iso)
        finally:
            conn.close()
        print("Sincronização concluída.")
        return 0

    return _executar_buscar(parser, args, argv_norm, pasta_dados, pasta_saida)
