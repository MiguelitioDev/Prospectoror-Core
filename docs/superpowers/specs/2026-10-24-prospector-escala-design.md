# Prospector de Leads — escala nacional, histórico e enriquecimento gratuito

Data: 2026-10-24 · Base: `buscar_leads.py` (584 linhas, um arquivo só)

## Diagnóstico do sistema atual

- Fonte única: OpenStreetMap via Overpass, raio fixo de 6 km em volta de 8 pontos fixos
  (`CIDADES`). Fora desses pontos nada é buscado.
- Rodada real (`leads_2026-10-24_0616.xlsx`): 1056 leads, só **142 com telefone (13%)**,
  76 com WhatsApp, 45 com e-mail. Como lead sem contato tem a nota limitada a 15,
  **947 (90%) ficaram "Frio"**. O gargalo principal é **falta de contato**, não de geografia.
- Nenhum histórico: cada rodada traz de novo os mesmos estabelecimentos.
- Bug: telefone com zero na frente (`085 99999-8888`) não gera link de WhatsApp.
- Falha do Overpass devolve `[]`, igual a "cidade sem empresas" (falha silenciosa).
- `tourism=information` (posto de informação turística, quase sempre da prefeitura) vira "Agência".
- Planilha: aba "Resumo" depende de índices de linha fixos (1, 6, 11); sem links clicáveis,
  sem lista suspensa para "Status contato", tudo numa aba só.
- Verificação de sites é sequencial (timeout de 8 s cada).

## Requisitos

1. **Sem limitação geográfica.** Buscar por município inteiro (limite oficial), em qualquer
   UF ou no Brasil todo (`--uf todos`), ou em cidades escolhidas (`--cidade "Gramado/RS"`).
   Lista de municípios, centroide e população vêm da API do IBGE (grátis, sem chave).
2. **Escala com rodadas.** O Brasil tem 5.570 municípios; cada rodada varre no máximo
   `--max-municipios` (padrão 40), ordenados por população. Municípios varridos há menos de
   `--revarrer-dias` (padrão 90) são pulados. Interromper e rodar de novo continua de onde parou.
3. **Não repetir leads.** Banco SQLite local guarda todo lead encontrado e quais já saíram em
   planilha. Uma rodada só exporta leads nunca exportados. Os 1056 leads da planilha antiga que
   tinham algum contato contam como já exportados (os sem contato podem voltar se ganharem contato).
4. **Fila.** Leads encontrados e não exportados (acima do `--limite`, padrão 300) ficam na fila e
   saem nas próximas rodadas, sem nova consulta ao Overpass.
5. **Retorno da planilha.** O que você preencher em "Status contato", "Valor fechado (R$)" e
   "Observações" volta para o banco no começo da próxima rodada. "Sem interesse" e
   "Não contatar" bloqueiam o lead para sempre.
6. **Mais contatos (grátis).** Base aberta de CNPJ da Receita Federal (mensal, ~5,4 GB de
   "Estabelecimentos"): telefone, e-mail, endereço, CNAE e data de abertura de toda empresa ativa.
   Usada para (a) completar contato dos leads do OSM e (b) trazer empresas que nem estão no mapa.
   Empresa aberta há menos de 18 meses ganha pontos ("ainda montando presença online").
   É um comando separado e opcional (`python buscar_leads.py cnpj`).
7. **Planilha melhor.** Abas "Abordar" (com contato), "Pesquisar contato" (sem contato, opcional),
   "Resumo" e "Rodada". Tabela do Excel com filtro, links clicáveis (WhatsApp com mensagem pronta,
   Google Maps, site), lista suspensa em "Status contato", coluna "ID" para a sincronização.
8. **Mantém** a lógica atual de nota, preço, protótipo/site final e os pesos (não-regressão).

## Fontes gratuitas confirmadas em 2026-10-24

| Fonte | Endpoint | Uso |
|---|---|---|
| IBGE municípios | `https://servicodados.ibge.gov.br/api/v1/localidades/estados/{UF}/municipios` | código IBGE + nome |
| IBGE estados | `https://servicodados.ibge.gov.br/api/v1/localidades/estados` | id numérico da UF |
| IBGE centroides | `https://servicodados.ibge.gov.br/api/v3/malhas/estados/{id_uf}/metadados?intrarregiao=municipio` | `centroide.latitude/longitude` |
| IBGE população | `https://servicodados.ibge.gov.br/api/v3/agregados/6579/periodos/-1/variaveis/9324?localidades=N6[N3[{id_uf}]]` | ordenar por porte |
| Overpass por município | `area["IBGE:GEOCODIGO"="2304400"]["admin_level"="8"]->.a;` | testado, funciona |
| Receita CNPJ (WebDAV público) | `https://arquivos.receitafederal.gov.br/public.php/webdav/{AAAA-MM}/` usuário `YggdBLfdninEJX9`, senha vazia | `Estabelecimentos0..9.zip`, `Municipios.zip` |

Formato `Estabelecimentos*.csv`: sem cabeçalho, `;`, aspas, latin-1, 30 colunas
(0-2 CNPJ, 4 nome fantasia, 5 situação `02`=ativa, 10 início `AAAAMMDD`, 11 CNAE principal,
13-15 logradouro, 17 bairro, 18 CEP, 19 UF, 20 município **código da Receita (não é IBGE)**,
21-22 DDD+tel1, 23-24 DDD+tel2, 27 e-mail). Há `;` dentro de aspas: usar `csv.reader`.
`Municipios.csv`: `"1389";"FORTALEZA"` — sem UF; o mapeamento para IBGE é por (UF da linha, nome).

## Fora do escopo

Google Maps/Places (exige cartão ou viola os termos), raspagem de Instagram, envio automático
de mensagens, interface gráfica.
