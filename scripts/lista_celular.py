"""Converte a planilha mais recente de leads em uma lista Markdown legível no celular.

Uso: python scripts/lista_celular.py PASTA_SAIDA ARQUIVO_MD
"""
from pathlib import Path
import sys

from openpyxl import load_workbook

ICONES = {"Quente": "🔥", "Morno": "🟡", "Frio": "⚪"}


def _txt(valor) -> str:
    return str(valor or "").strip()


def _linha_para_md(i: int, lead: dict) -> str:
    icone = ICONES.get(_txt(lead.get("Prioridade")), "•")
    titulo = f"### {i}. {icone} {_txt(lead.get('Nome'))}"
    sub = " · ".join(
        p for p in (
            _txt(lead.get("Tipo")),
            f"{_txt(lead.get('Cidade'))}/{_txt(lead.get('UF'))}",
            f"chance {_txt(lead.get('Chance de venda'))}" if lead.get("Chance de venda") != "" else "",
        ) if p
    )
    linhas = [titulo, sub]
    if _txt(lead.get("Site")):
        linhas.append(f"Site: {_txt(lead.get('Site'))}")
    if _txt(lead.get("Preparar")):
        linhas.append(f"Preparar: **{_txt(lead.get('Preparar'))}**")
    if _txt(lead.get("Oferta inicial (R$)")):
        linhas.append(
            f"Oferta R$ {_txt(lead.get('Oferta inicial (R$)'))} · "
            f"alvo R$ {_txt(lead.get('Valor alvo (R$)'))} · "
            f"mín. R$ {_txt(lead.get('Mínimo (R$)'))}"
        )
    acoes = []
    if _txt(lead.get("Abrir conversa")):
        acoes.append(f"[💬 WhatsApp]({_txt(lead.get('Abrir conversa'))})")
    if _txt(lead.get("Telefone")):
        acoes.append(f"[📞 {_txt(lead.get('Telefone'))}](tel:{_txt(lead.get('Telefone'))})")
    if _txt(lead.get("Ver no Google Maps")):
        acoes.append(f"[📍 Maps]({_txt(lead.get('Ver no Google Maps'))})")
    if _txt(lead.get("URL atual")):
        acoes.append(f"[🌐 Site atual]({_txt(lead.get('URL atual'))})")
    if acoes:
        linhas.append(" · ".join(acoes))
    return "\n\n".join(linhas)


def main(pasta_saida: str, arquivo_md: str) -> int:
    planilhas = sorted(Path(pasta_saida).glob("leads_*.xlsx"))
    if not planilhas:
        Path(arquivo_md).write_text("Nenhuma planilha encontrada.\n", encoding="utf-8")
        return 0
    wb = load_workbook(planilhas[-1], data_only=True)
    ws = wb["Abordar"] if "Abordar" in wb.sheetnames else wb.worksheets[0]
    linhas = list(ws.iter_rows(values_only=True))
    if len(linhas) < 2:
        Path(arquivo_md).write_text("Nenhum lead novo nesta rodada.\n", encoding="utf-8")
        return 0
    cab = [str(c or "") for c in linhas[0]]
    leads = [dict(zip(cab, ["" if v is None else v for v in lin])) for lin in linhas[1:]]
    leads = [l for l in leads if _txt(l.get("Nome"))]

    cabecalho = f"# Leads — {planilhas[-1].stem.replace('leads_', '')}\n\n{len(leads)} leads novos, do melhor para o pior."
    corpo = [_linha_para_md(i, l) for i, l in enumerate(leads, start=1)]
    Path(arquivo_md).write_text("\n\n---\n\n".join([cabecalho, *corpo]) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
