"""Exporta os leads de cada rodada para o arquivo JSON que o app de celular lê.

O arquivo é acumulativo: cada rodada acrescenta os leads novos e guarda os
anteriores, para o app mostrar todo o histórico de prospecção. As colunas que
o usuário preenche (status, valor fechado, observações) ficam no próprio app,
não neste arquivo.
"""

import json
import os
from pathlib import Path

VERSAO = 1
MAX_RODADAS = 50
MAX_LEADS = 5000

# Campos que o app não usa ou que são preenchidos no próprio app
_IGNORAR = {
    "Nota Google (conferir)",
    "Status contato",
    "Valor fechado (R$)",
    "Observações",
}


def _limpar(linha: dict) -> dict:
    """Remove chaves internas (prefixo _) e campos preenchidos pelo usuário."""
    return {k: v for k, v in linha.items() if not k.startswith("_") and k not in _IGNORAR}


def ler(caminho: Path) -> dict:
    """Lê o JSON existente ou devolve uma estrutura vazia se não existir/estiver corrompido."""
    caminho = Path(caminho)
    vazio = {"versao": VERSAO, "atualizado": "", "rodadas": [], "leads": []}
    if not caminho.exists():
        return vazio
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return vazio
    if not isinstance(dados, dict) or not isinstance(dados.get("leads"), list):
        return vazio
    dados.setdefault("rodadas", [])
    return dados


def acrescentar(caminho: Path, abordar: list[dict], pesquisar: list[dict],
                info_rodada: dict, agora_iso: str) -> int:
    """Acrescenta os leads da rodada ao JSON. Devolve quantos leads novos entraram."""
    caminho = Path(caminho)
    dados = ler(caminho)

    existentes = {str(l.get("ID")): i for i, l in enumerate(dados["leads"])}
    novos = 0
    for lista, aba in ((abordar, "Abordar"), (pesquisar, "Pesquisar contato")):
        for linha in lista:
            item = _limpar(linha)
            item["Aba"] = aba
            item["Exportado em"] = agora_iso
            lead_id = str(item.get("ID") or "")
            if not lead_id:
                continue
            if lead_id in existentes:
                antigo = dados["leads"][existentes[lead_id]]
                item["Exportado em"] = antigo.get("Exportado em", agora_iso)
                dados["leads"][existentes[lead_id]] = item
            else:
                existentes[lead_id] = len(dados["leads"])
                dados["leads"].append(item)
                novos += 1

    # Mantém os mais recentes se passar do limite
    if len(dados["leads"]) > MAX_LEADS:
        dados["leads"] = dados["leads"][-MAX_LEADS:]

    dados["rodadas"] = (dados["rodadas"] + [dict(info_rodada)])[-MAX_RODADAS:]
    dados["versao"] = VERSAO
    dados["atualizado"] = agora_iso

    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(caminho.suffix + ".tmp")
    temporario.write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")),
                          encoding="utf-8")
    os.replace(temporario, caminho)
    return novos


def registrar_rodada_vazia(caminho: Path, info_rodada: dict, agora_iso: str) -> None:
    """Registra uma rodada sem leads novos, para o app mostrar quando foi a última busca."""
    acrescentar(caminho, [], [], info_rodada, agora_iso)
