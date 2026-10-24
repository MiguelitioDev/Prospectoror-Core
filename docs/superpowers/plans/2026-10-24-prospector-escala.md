# Prospector de Leads — Plano de Implementação

> **Para agentes (Antigravity ou outro):** execute tarefa por tarefa, na ordem. Cada tarefa
> segue TDD: teste falhando → código → teste passando → commit. Marque os checkboxes (`- [ ]`).
> Não pule para a tarefa seguinte com teste vermelho. Leia a especificação antes de começar.

**Goal:** Transformar `buscar_leads.py` num prospector que busca em qualquer município do Brasil,
nunca repete leads entre rodadas, completa contatos com a base aberta de CNPJ e gera uma planilha
organizada que devolve o andamento das vendas para o banco.

**Architecture:** Pacote `prospector/` com um módulo por responsabilidade (IBGE, OSM, CNPJ,
pontuação, histórico SQLite, planilha, CLI). `buscar_leads.py` vira só o ponto de entrada.
A lógica de nota/preço/entregas atual é **movida sem mudar o comportamento** e travada por
testes de não-regressão antes de qualquer alteração.

**Tech Stack:** Python 3.13 · requests · openpyxl · phonenumbers · rapidfuzz · tqdm ·
sqlite3/argparse/concurrent.futures/csv/zipfile (biblioteca padrão) · pytest.

**Spec:** `docs/superpowers/specs/2026-10-24-prospector-escala-design.md`

## Global Constraints

- Tudo gratuito, sem chave de API, sem cadastro, sem cartão.
- Windows 11 + PowerShell. Comandos: `python -m pytest`, `python -m pip`. Caminhos com `pathlib`.
- Testes **nunca** acessam a internet: `requests` sempre substituído por `monkeypatch`/fakes.
- Textos de interface, colunas, mensagens e nomes de funções em **português**, como no código atual.
- Nomes de colunas atuais da planilha são mantidos exatamente (ex.: `"Chance de venda"`,
  `"Oferta inicial (R$)"`, `"Status contato"`); colunas novas: `"ID"`, `"Fonte"`, `"UF"`,
  `"CNPJ"`, `"Aberta em"`, `"Abrir conversa"`.
- Overpass: uma consulta por vez, `time.sleep(2)` entre municípios, `User-Agent` de `config.HEADERS`.
- Banco: `dados/prospector.db`. Base CNPJ: `dados/cnpj.db`. Cache IBGE: `dados/ibge/`.
- `.gitignore`: `dados/`, `*.xlsx`, `__pycache__/`, `.pytest_cache/`.
- Datas gravadas como texto ISO (`datetime.now().isoformat(timespec="seconds")`).

## Review Focus

1. **Overpass falha ou responde 200 com `remark` de erro/timeout** → `consultar_overpass` devolve
   `None`, o município **não** é marcado como varrido e entra na próxima rodada. (Tarefa 4 e 7)
2. **Planilha aberta no Excel** → ao sincronizar, arquivo ilegível gera aviso e a rodada continua;
   ao salvar, `PermissionError` salva com sufixo `_2`. Os leads só são marcados como exportados
   **depois** que o arquivo foi salvo. (Tarefa 6 e 7)
3. **Nomes genéricos no cruzamento OSM × Receita** ("Restaurante", "Pousada", "Bar do Centro" ×
   "Bar") → não casam; só casa nome com núcleo ≥ 4 letras após tirar palavras genéricas, ou
   telefone igual. (Tarefa 9)
4. **Interrupção no meio (Ctrl+C, queda de internet)** → cada município é gravado e comitado ao
   terminar; rodar de novo continua sem duplicar. (Tarefa 5 e 7)
5. **Usuário mexe na planilha** (apaga linhas, reordena, apaga a coluna Observações, linha sem ID)
   → sincronização casa por `ID`, ignora linhas sem ID e colunas ausentes, não quebra. (Tarefa 6)

---

## Estrutura de arquivos

```
buscar_leads.py              # só: from prospector.cli import main; raise SystemExit(main())
requirements.txt
.gitignore
README.md                    # como usar (Tarefa 7, completado na 9)
prospector/
  __init__.py
  config.py                  # todas as constantes (as atuais + novas)
  modelos.py                 # dataclasses Municipio, Lead, Estab
  texto.py                   # normalizar_nome, nucleo_nome, normalizar_telefone, link_whatsapp
  ibge.py                    # municípios, centroides, população (com cache)
  osm.py                     # consulta Overpass por município → Lead
  sites.py                   # site_no_ar + verificação em paralelo
  pontuacao.py               # nota, preço, sites, entregas, pontuar(lead) → linha da planilha
  historico.py               # SQLite: leads, varreduras, rodadas, legado, sincronização
  planilha.py                # gerar_planilha, ler_status
  cnpj.py                    # baixar/construir base Receita, cruzar com leads
  cli.py                     # argparse + orquestração
tests/
  conftest.py                # fixture fazer_lead(**campos)
  test_pontuacao.py  test_texto.py  test_ibge.py  test_osm.py  test_sites.py
  test_historico.py  test_planilha.py  test_cli.py  test_cnpj.py
```

## Modelos compartilhados (definidos na Tarefa 1, usados por todas)

```python
# prospector/modelos.py
@dataclass
class Municipio:
    ibge: str          # "2304400"
    nome: str          # "Fortaleza"
    uf: str            # "CE"
    lat: float
    lng: float
    populacao: int = 0

@dataclass
class Lead:
    id: str                    # "osm:node/123" | "cnpj:12345678000190"
    fonte: str                 # "OSM" | "Receita" | "OSM+Receita"
    nome: str
    tipo: str                  # chave de config.PESO_TIPO
    municipio_ibge: str
    cidade: str
    uf: str
    lat: float
    lng: float
    tags: dict = field(default_factory=dict)   # tags OSM; {} ou sintéticas p/ Receita
    site: str = ""
    redes: str = ""
    telefone: str = ""         # E.164: "+5585999998888"
    whatsapp: str = ""         # "https://wa.me/5585999998888"
    email: str = ""
    cnpj: str = ""             # 14 dígitos
    abertura: str = ""         # "AAAA-MM-DD"
    status_site: str = ""      # "Sem site" | "Só rede social" | "A verificar" | "Tem site"
                               # | "Site fora do ar" | "Não conferido"
    def tem_contato(self) -> bool: ...   # telefone or email or redes or whatsapp
    def para_dict(self) -> dict: ...     # dataclasses.asdict
    @classmethod
    def de_dict(cls, d: dict) -> "Lead": ...

@dataclass
class Estab:
    cnpj: str; nome: str; cnae: str; tipo: str; municipio_ibge: str; uf: str
    logradouro: str; bairro: str; cep: str; telefone: str; telefone2: str
    email: str; abertura: str
```

---

### Task 1: Base do projeto + mover a lógica atual com testes de não-regressão

**Files:**
- Create: `requirements.txt`, `.gitignore`, `prospector/__init__.py`, `prospector/config.py`,
  `prospector/modelos.py`, `prospector/pontuacao.py`, `tests/conftest.py`, `tests/test_pontuacao.py`
- Modify: `buscar_leads.py` (permanece intacto nesta tarefa; só é reduzido na Tarefa 7)

**Interfaces:**
- Produces: `prospector.config` (todas as constantes de `buscar_leads.py:53-161`, **exceto**
  `CIDADES` e `ARQUIVO_SAIDA`); `prospector.modelos` (acima); em `prospector.pontuacao`, com as
  mesmas assinaturas e corpos de hoje: `distancia_km(lat, lng) -> float`, `faixa(km) -> str`,
  `numero(valor) -> int`, `calcular_chance(tags, tipo, status, telefone, whatsapp, email, redes,
  abordagem) -> tuple[int, list[str]]`, `calcular_preco(tags, tipo, status) -> tuple[int,int,int]`,
  `descrever_sites(tags, tipo, status) -> tuple[str,str]`, `definir_entregas(lista) -> None`,
  `classificar(nota) -> str`. Fixture `fazer_lead(**campos) -> Lead` (valores padrão: id
  `"osm:node/1"`, fonte `"OSM"`, nome `"Pousada Teste"`, tipo `"Pousada/Hotel"`, município
  `"2304400"`, cidade `"Fortaleza"`, uf `"CE"`, lat `-3.73`, lng `-38.52`, status `"Sem site"`).

- [ ] **Step 1: Inicializar git e congelar o estado original**

```powershell
git init
git add buscar_leads.py
git commit -m "chore: estado original do buscar_leads.py"
```

- [ ] **Step 2: Criar `requirements.txt`** com `requests>=2.32`, `openpyxl>=3.1`,
`phonenumbers>=8.13`, `rapidfuzz>=3.9`, `tqdm>=4.66`, `pytest>=8`; criar `.gitignore` (ver
Global Constraints). Rodar `python -m pip install -r requirements.txt`.

- [ ] **Step 3: Escrever os testes de não-regressão** (valores medidos no código atual)

```python
# tests/test_pontuacao.py
from prospector.pontuacao import calcular_chance, calcular_preco

def test_chance_pousada_completa():
    tags = {"tourism": "guest_house", "opening_hours": "24/7", "addr:street": "Rua X", "stars": "3"}
    nota, motivos = calcular_chance(tags, "Pousada/Hotel", "Sem site", "+55 85 99999-8888",
                                    "https://wa.me/5585999998888", "", "", "Presencial")
    assert nota == 85
    assert motivos == ["não tem site", "tem WhatsApp", "negócio bem estruturado",
                       "depende de turista reservando online", "dá para visitar pessoalmente"]

def test_chance_franquia_zera():
    nota, motivos = calcular_chance({"amenity": "restaurant", "brand": "X"}, "Restaurante",
                                    "Tem site", "", "", "a@b.com", "", "Mensagem")
    assert nota == 0
    assert "rede/franquia: decisão fora do local" in motivos

def test_chance_sem_contato_limitada_a_15():
    nota, motivos = calcular_chance({"amenity": "bar"}, "Bar/Café", "Sem site", "", "", "", "", "Ligação")
    assert nota == 15 and motivos[-1] == "sem contato público"

def test_preco_hotel_4_estrelas_fora_do_ar():
    assert calcular_preco({"tourism": "hotel", "stars": "4", "rooms": "20"},
                          "Pousada/Hotel", "Site fora do ar") == (3350, 2400, 2050)

def test_preco_cafe_com_site_respeita_minimo():
    assert calcular_preco({"amenity": "cafe"}, "Bar/Café", "Tem site") == (1150, 800, 800)
```

- [ ] **Step 4: Rodar e ver falhar** — `python -m pytest tests/test_pontuacao.py -v` →
FAIL `ModuleNotFoundError: prospector`.

- [ ] **Step 5: Criar `config.py`, `modelos.py`, `pontuacao.py`** copiando constantes e funções
de `buscar_leads.py` **sem alterar corpos**. `pontuacao.py` importa constantes de `config`.

- [ ] **Step 6: Rodar** — `python -m pytest -v` → 5 PASS.

- [ ] **Step 7: Commit** — `git add -A; git commit -m "refactor: pacote prospector com pontuação travada por testes"`

---

### Task 2: Texto e telefone (phonenumbers)

**Files:**
- Create: `prospector/texto.py`, `tests/test_texto.py`
- Modify: `prospector/config.py` (adicionar `STOPWORDS_NOME`)

**Interfaces:**
- Produces:
  - `normalizar_nome(nome: str) -> str` — NFKD sem acento, minúsculas, não-alfanumérico vira
    espaço, espaços colapsados.
  - `nucleo_nome(nome: str) -> str` — `normalizar_nome` sem as palavras de `config.STOPWORDS_NOME`
    = `{"pousada","hotel","hostel","restaurante","bar","cafe","lanchonete","loja","ltda","me",
    "eireli","epp","sa","de","da","do","das","dos","e","o","a"}`.
  - `normalizar_telefone(bruto: str, ddd: str = "") -> str` — E.164 `"+55..."` ou `""`.
    Usa `phonenumbers.parse(..., "BR")`; antes de parsear, remove um `0` inicial de tronco;
    se vier `ddd` separado (Receita) e o número tiver 8 dígitos começando em 6-9, prefixa `9`.
    Só o primeiro número quando houver `;`.
  - `link_whatsapp(telefone_e164: str) -> str` — `"https://wa.me/55..."` só se
    `phonenumbers.number_type` for `MOBILE`; senão `""`.

- [ ] **Step 1: Teste falhando**

```python
# tests/test_texto.py
import pytest
from prospector.texto import normalizar_nome, nucleo_nome, normalizar_telefone, link_whatsapp

def test_normalizar_nome():
    assert normalizar_nome("  Pousada Ôlá-Mar! ") == "pousada ola mar"

def test_nucleo_nome_tira_genericos():
    assert nucleo_nome("Restaurante do Zé Ltda") == "ze"
    assert nucleo_nome("Pousada") == ""

@pytest.mark.parametrize("bruto,ddd,esperado", [
    ("(85) 99999-8888", "", "+5585999998888"),
    ("+55 85 99999-8888", "", "+5585999998888"),
    ("085 99999-8888", "", "+5585999998888"),       # bug atual: zero de tronco
    ("(85) 3222-1111", "", "+558532221111"),
    ("+55 (54) 9 9988-7766; 3222-0000", "", "+5554999887766"),
    ("88776655", "85", "+5585988776655"),           # celular antigo sem o 9 (Receita)
    ("32221111", "85", "+558532221111"),
    ("abc", "", ""),
])
def test_normalizar_telefone(bruto, ddd, esperado):
    assert normalizar_telefone(bruto, ddd) == esperado

def test_link_whatsapp_so_celular():
    assert link_whatsapp("+5585999998888") == "https://wa.me/5585999998888"
    assert link_whatsapp("+558532221111") == ""
    assert link_whatsapp("") == ""
```

- [ ] **Step 2:** `python -m pytest tests/test_texto.py -v` → FAIL (módulo não existe).
- [ ] **Step 3:** Implementar `prospector/texto.py` com as assinaturas acima.
- [ ] **Step 4:** `python -m pytest -v` → tudo PASS.
- [ ] **Step 5:** `git add -A; git commit -m "feat: normalização de nome e telefone com phonenumbers"`

---

### Task 3: Municípios do IBGE (fim do limite de estados)

**Files:**
- Create: `prospector/ibge.py`, `tests/test_ibge.py`
- Modify: `prospector/config.py` (adicionar `UFS` = as 27 siglas, `IBGE_CACHE_DIAS = 30`)

**Interfaces:**
- Consumes: `Municipio`, `texto.normalizar_nome`.
- Produces:
  - `listar_municipios(ufs: list[str], cache_dir: Path) -> list[Municipio]` — `["todos"]`
    expande para `config.UFS`. Para cada UF: id numérico (endpoint estados), lista de municípios,
    centroides e população (endpoints na spec). Junta por código IBGE; município sem centroide
    usa (0, 0) e sem população usa 0. Cache JSON `cache_dir/{UF}.json` válido por
    `IBGE_CACHE_DIAS`. Sigla inválida → `ValueError("UF desconhecida: XX")`.
  - `achar_cidade(texto: str, municipios: list[Municipio]) -> Municipio` — aceita
    `"Gramado/RS"`, `"Gramado - RS"`, `"gramado rs"`; compara com `normalizar_nome`.
    Não achou → `ValueError` com a mensagem `"Cidade não encontrada: <texto>"`.

- [ ] **Step 1: Teste falhando** — fixtures `fake_ibge` e `muns_ce` no próprio `test_ibge.py`; usar um `FakeSession`/`monkeypatch` em `requests.get` que
responde por URL com JSON mínimo (2 municípios de CE: `2304400 Fortaleza`, `2303709 Caucaia`).

```python
def test_listar_municipios_junta_centroide_e_populacao(fake_ibge, tmp_path):
    muns = listar_municipios(["CE"], tmp_path)
    fort = next(m for m in muns if m.ibge == "2304400")
    assert (fort.nome, fort.uf, fort.lat, fort.lng, fort.populacao) == ("Fortaleza", "CE", -3.7858, -38.528, 2574412)

def test_listar_municipios_usa_cache(fake_ibge, tmp_path):
    listar_municipios(["CE"], tmp_path)
    fake_ibge.chamadas.clear()
    listar_municipios(["CE"], tmp_path)
    assert fake_ibge.chamadas == []

def test_uf_invalida(tmp_path):
    with pytest.raises(ValueError, match="UF desconhecida: XX"):
        listar_municipios(["XX"], tmp_path)

@pytest.mark.parametrize("texto", ["Fortaleza/CE", "fortaleza - ce", "FORTALEZA CE"])
def test_achar_cidade(texto, muns_ce):
    assert achar_cidade(texto, muns_ce).ibge == "2304400"
```

- [ ] **Step 2:** rodar → FAIL. **Step 3:** implementar. **Step 4:** `python -m pytest -v` → PASS.
- [ ] **Step 5:** `git commit -am "feat: municípios, centroides e população via IBGE"` (após `git add -A`).

---

### Task 4: Overpass por município inteiro

**Files:**
- Create: `prospector/osm.py`, `tests/test_osm.py`
- Modify: `prospector/config.py` (adicionar `"https://overpass.private.coffee/api/interpreter"`
  ao fim de `SERVIDORES`; `ORGAO_PUBLICO = r"prefeitura|secretaria|governo|setur|municipal"`)

**Interfaces:**
- Consumes: `Municipio`, `Lead`, `texto.normalizar_telefone`, `texto.link_whatsapp`, `config.TIPOS`.
- Produces:
  - `montar_consulta_area(ibge: str, tipos: dict[str, list[str]]) -> str` — formato exato:
    `[out:json][timeout:180];area["IBGE:GEOCODIGO"="{ibge}"]["admin_level"="8"]->.a;(` +
    `nwr[{filtro}]["name"](area.a);` por filtro + `);out center tags;`
  - `consultar_overpass(consulta: str) -> list[dict] | None` — mesma rotação/tentativas de hoje;
    devolve `None` se todos falharem **ou** se o JSON tiver `"remark"` contendo `"runtime error"`
    ou `"timed out"`. HTTP 429 espera 30 s antes de tentar o próximo.
  - `identificar_tipo(tags) -> str`, `pegar_site`, `pegar_redes`, `pegar_email` — movidos de
    `buscar_leads.py` sem mudança.
  - `elemento_para_lead(el: dict, mun: Municipio) -> Lead | None` — `None` se sem nome ou se
    `tourism=information` com `name`/`operator` casando `config.ORGAO_PUBLICO` (sem diferenciar
    maiúsculas). `status_site`: sem site → `"Só rede social"` se houver redes senão `"Sem site"`;
    domínio de `SO_REDE_SOCIAL` → `"Só rede social"`; outro site → `"A verificar"`.
    Telefone via `normalizar_telefone` (chaves `phone`, `contact:phone`, `contact:mobile`,
    `contact:whatsapp`), WhatsApp via `link_whatsapp`.
  - `buscar_municipio(mun: Municipio, tipos: dict) -> list[Lead] | None` — `None` repassa a falha.

- [ ] **Step 1: Testes falhando**

```python
def test_consulta_usa_codigo_ibge():
    q = montar_consulta_area("2304400", {"X": ['"amenity"="bar"']})
    assert 'area["IBGE:GEOCODIGO"="2304400"]["admin_level"="8"]->.a;' in q
    assert 'nwr["amenity"="bar"]["name"](area.a);' in q

def test_remark_de_erro_vira_none(monkeypatch):
    responder(monkeypatch, 200, {"elements": [{"type": "node", "id": 1}], "remark": "runtime error: Query timed out"})
    assert consultar_overpass("q") is None

def test_todos_servidores_falhando_vira_none(monkeypatch):
    responder(monkeypatch, 504, {})
    assert consultar_overpass("q") is None

def test_cidade_sem_empresas_vira_lista_vazia(monkeypatch):
    responder(monkeypatch, 200, {"elements": []})
    assert consultar_overpass("q") == []

def test_posto_de_informacao_da_prefeitura_e_ignorado(mun_fortaleza):
    el = {"type": "node", "id": 5, "lat": -3.7, "lon": -38.5,
          "tags": {"name": "Posto de Informação Turística", "tourism": "information",
                   "information": "office", "operator": "Prefeitura de Fortaleza"}}
    assert elemento_para_lead(el, mun_fortaleza) is None

def test_elemento_vira_lead(mun_fortaleza):
    el = {"type": "way", "id": 9, "center": {"lat": -3.7, "lon": -38.5},
          "tags": {"name": "Pousada Sol", "tourism": "guest_house", "phone": "085 99999-8888",
                   "website": "https://pousadasol.com.br"}}
    lead = elemento_para_lead(el, mun_fortaleza)
    assert lead.id == "osm:way/9" and lead.fonte == "OSM" and lead.tipo == "Pousada/Hotel"
    assert lead.telefone == "+5585999998888" and lead.whatsapp == "https://wa.me/5585999998888"
    assert lead.status_site == "A verificar" and (lead.lat, lead.lng) == (-3.7, -38.5)
```

(`responder` = helper no próprio arquivo que faz `monkeypatch.setattr(requests, "post", ...)` e
`monkeypatch.setattr(time, "sleep", lambda s: None)`.)

- [ ] **Step 2:** rodar → FAIL. **Step 3:** implementar. **Step 4:** `python -m pytest -v` → PASS.
- [ ] **Step 5:** `git add -A; git commit -m "feat: busca Overpass por município (IBGE:GEOCODIGO)"`

---

### Task 5: Histórico SQLite (não repetir leads)

**Files:**
- Create: `prospector/historico.py`, `tests/test_historico.py`

**Interfaces:**
- Consumes: `Lead`, `texto.normalizar_nome`.
- Produces (todas recebem `conn: sqlite3.Connection`; cada função de escrita faz `conn.commit()`):
  - `abrir(caminho: Path) -> sqlite3.Connection` — cria pasta e tabelas:
    - `leads(id TEXT PK, nome_norm TEXT, uf TEXT, municipio_ibge TEXT, dados TEXT /*json*/,
      primeira_vez TEXT, visto_em TEXT, exportado_em TEXT, rodada INTEGER,
      status_contato TEXT DEFAULT '', valor_fechado TEXT DEFAULT '', observacoes TEXT DEFAULT '',
      bloqueado INTEGER DEFAULT 0)`
    - `varreduras(municipio_ibge TEXT, fonte TEXT, varrido_em TEXT, PRIMARY KEY(municipio_ibge, fonte))`
    - `rodadas(id INTEGER PK AUTOINCREMENT, criada_em TEXT, arquivo TEXT, parametros TEXT)`
    - `legado(nome_norm TEXT, uf TEXT, PRIMARY KEY(nome_norm, uf))`
    - `arquivos_importados(caminho TEXT PRIMARY KEY, importado_em TEXT)`
  - `salvar_leads(conn, leads: list[Lead], agora: str) -> int` — upsert; devolve quantos eram
    novos. Em lead existente: atualiza `dados` e `visto_em`, preserva `primeira_vez`,
    `exportado_em`, status/valor/observações/bloqueio; **não apaga contato** (campo vazio no novo
    mantém o antigo); se o novo `status_site == "A verificar"`, o `site` é igual e o antigo é
    `"Tem site"`/`"Site fora do ar"`, mantém o antigo.
  - `marcar_varrido(conn, municipio_ibge: str, fonte: str, agora: str) -> None`
  - `municipios_varridos(conn, fonte: str, desde: str) -> set[str]` — varridos com `varrido_em >= desde`.
  - `pendentes(conn) -> list[Lead]` — `exportado_em IS NULL`, `bloqueado = 0` e `(nome_norm, uf)`
    fora de `legado`.
  - `nova_rodada(conn, arquivo: str, parametros: dict, agora: str) -> int`
  - `marcar_exportados(conn, ids: list[str], rodada: int, agora: str) -> None`
  - `atualizar_status(conn, linhas: list[dict]) -> int` — cada dict com `"ID"` e opcionalmente
    `"Status contato"`, `"Valor fechado (R$)"`, `"Observações"`; ignora ID desconhecido e chave
    ausente; status em `config.STATUS_BLOQUEIO = {"Sem interesse", "Não contatar"}` → `bloqueado=1`.
  - `importar_legado(conn, linhas: list[dict]) -> int` — linhas da planilha antiga (sem coluna
    ID); só importa as que têm `Telefone`, `E-mail`, `WhatsApp` ou `Redes sociais`; UF = texto
    depois de `" - "` em `Cidade` (`"Cumbuco - CE"` → `"CE"`).

- [ ] **Step 1: Testes falhando** (banco em `tmp_path`)

```python
def test_lead_novo_e_repetido(conn, fazer_lead):
    assert salvar_leads(conn, [fazer_lead(id="osm:node/1")], "2026-10-24T10:00:00") == 1
    assert salvar_leads(conn, [fazer_lead(id="osm:node/1")], "2026-10-25T10:00:00") == 0
    assert len(pendentes(conn)) == 1

def test_exportado_nao_volta(conn, fazer_lead):
    salvar_leads(conn, [fazer_lead(id="osm:node/1"), fazer_lead(id="osm:node/2")], "t")
    r = nova_rodada(conn, "leads_x.xlsx", {}, "t")
    marcar_exportados(conn, ["osm:node/1"], r, "t")
    salvar_leads(conn, [fazer_lead(id="osm:node/1")], "t2")      # achado de novo numa revarredura
    assert [l.id for l in pendentes(conn)] == ["osm:node/2"]

def test_revarredura_nao_apaga_contato_nem_status_verificado(conn, fazer_lead):
    salvar_leads(conn, [fazer_lead(id="osm:node/1", telefone="+5585999998888",
                                   site="https://a.com", status_site="Site fora do ar")], "t")
    salvar_leads(conn, [fazer_lead(id="osm:node/1", telefone="", site="https://a.com",
                                   status_site="A verificar")], "t2")
    l = pendentes(conn)[0]
    assert l.telefone == "+5585999998888" and l.status_site == "Site fora do ar"

def test_bloqueio_por_status(conn, fazer_lead):
    salvar_leads(conn, [fazer_lead(id="osm:node/1")], "t")
    assert atualizar_status(conn, [{"ID": "osm:node/1", "Status contato": "Não contatar"},
                                   {"ID": "nao-existe", "Status contato": "Fechado"},
                                   {"Status contato": "Fechado"}]) == 1
    assert pendentes(conn) == []

def test_legado_com_contato_bloqueia_mesmo_nome_e_uf(conn, fazer_lead):
    importar_legado(conn, [
        {"Nome": "Pousada Sol", "Cidade": "Cumbuco - CE", "Telefone": "(85) 3222-1111"},
        {"Nome": "Bar Sem Contato", "Cidade": "Cumbuco - CE"},
    ])
    salvar_leads(conn, [fazer_lead(id="osm:node/1", nome="POUSADA SOL", uf="CE"),
                        fazer_lead(id="osm:node/2", nome="Pousada Sol", uf="RN"),
                        fazer_lead(id="osm:node/3", nome="Bar Sem Contato", uf="CE")], "t")
    assert sorted(l.id for l in pendentes(conn)) == ["osm:node/2", "osm:node/3"]

def test_varreduras(conn):
    marcar_varrido(conn, "2304400", "osm", "2026-10-01T00:00:00")
    assert municipios_varridos(conn, "osm", "2026-07-01T00:00:00") == {"2304400"}
    assert municipios_varridos(conn, "osm", "2026-10-02T00:00:00") == set()
```

- [ ] **Step 2:** rodar → FAIL. **Step 3:** implementar. **Step 4:** `python -m pytest -v` → PASS.
- [ ] **Step 5:** `git add -A; git commit -m "feat: histórico SQLite para não repetir leads"`

---

### Task 6: Planilha nova + leitura de volta

**Files:**
- Create: `prospector/planilha.py`, `tests/test_planilha.py`
- Modify: `prospector/pontuacao.py` (adicionar `pontuar`), `prospector/config.py`
  (`STATUS_CONTATO`, `MENSAGENS`, `MENSAGEM_PADRAO`), `tests/test_pontuacao.py`

**Interfaces:**
- Consumes: `Lead`, funções de `pontuacao` da Tarefa 1.
- Produces:
  - `config.STATUS_CONTATO = ["Mensagem enviada", "Respondeu", "Reunião marcada",
    "Proposta enviada", "Fechado", "Sem interesse", "Não contatar"]`
  - `config.MENSAGEM_PADRAO = "Olá! Vi a {nome} aqui em {cidade} e preparei uma ideia de site para vocês, com contato direto pelo WhatsApp. Posso te mostrar em 2 minutos?"`
    e `config.MENSAGENS: dict[str, str]` por tipo (mesmo formato, `{nome}` e `{cidade}`;
    o agente escreve uma por tipo de `PESO_TIPO`, citando o que o protótipo daquele nicho mostra).
  - `pontuacao.pontuar(lead: Lead, hoje: date | None = None) -> dict` — devolve a linha da
    planilha com as **mesmas chaves e ordem** do dict de `buscar_leads.py:470-500`, com
    `"Site"` = `lead.status_site`, `"Cidade"` = `lead.cidade`, e mais: `"UF"` logo após
    `"Cidade"`, `"Abrir conversa"` logo após `"WhatsApp"` (= `whatsapp + "?text=" +
    quote(mensagem)` ou `""`), e no fim `"Fonte"`, `"CNPJ"`, `"Aberta em"`, `"ID"`.
    `"Ver no Google Maps"` usa `f"{nome} {cidade} {uf}"`. Mantém `_proto`/`_final` para
    `definir_entregas`. `"Distância (km)"` usa `distancia_km(lead.lat, lead.lng)`.
    `"Não conferido"` precisa existir em `calcular_chance`/`calcular_preco`/`descrever_sites`:
    necessidade 25, motivo `"site não conferido (procure no Google)"`, preço sem fator.
    `"A verificar"` (quando rodou com `--sem-verificar-sites`) é tratado como `"Tem site"` dentro de `pontuar`.
  - `planilha.gerar_planilha(abordar: list[dict], pesquisar: list[dict], info: dict, caminho: Path) -> Path`
    - Aba **"Abordar"**: linhas de `abordar`, como Tabela do Excel (`openpyxl.worksheet.table.Table`,
      `displayName="Leads"`, estilo `TableStyleMedium2`), cores de "Prioridade" e "Preparar"
      atuais, larguras atuais, `freeze_panes="D2"`, formato `"R$" #,##0`, texto quebrado nas
      colunas longas. Hiperlinks clicáveis em `"Abrir conversa"`, `"WhatsApp"`,
      `"Ver no Google Maps"`, `"URL atual"`. `DataValidation(type="list")` com
      `STATUS_CONTATO` em toda a coluna `"Status contato"`.
    - Aba **"Pesquisar contato"**: só criada se `pesquisar` não for vazio; colunas `"Nome"`,
      `"Tipo"`, `"Cidade"`, `"UF"`, `"Chance de venda"`, `"Ver no Google Maps"`,
      `"Telefone"`, `"Observações"`, `"ID"`.
    - Aba **"Resumo"**: os três blocos atuais + bloco "Por cidade" (top 15 por nº de Quentes);
      linhas montadas em laço, **sem índices fixos**.
    - Aba **"Rodada"**: pares chave/valor de `info` (data, filtros, municípios varridos,
      faltam varrer, novos encontrados, exportados, fila restante).
    - Se salvar der `PermissionError`, salva em `<nome>_2.xlsx` e devolve esse caminho.
  - `planilha.ler_status(caminho: Path) -> list[dict]` — lê "Abordar" e "Pesquisar contato";
    devolve dicts com `"ID"` e as colunas `"Status contato"`, `"Valor fechado (R$)"`,
    `"Observações"` que existirem; pula linhas sem ID. Planilha **sem** coluna `"ID"` (formato
    antigo, aba "Leads") → `ValueError("formato antigo")`.
  - `planilha.ler_legado(caminho: Path) -> list[dict]` — aba "Leads" do formato antigo, cada
    linha como dict cabeçalho→valor.

- [ ] **Step 1: Testes falhando**

```python
def test_pontuar_mantem_colunas_e_acrescenta_novas(fazer_lead):
    linha = pontuar(fazer_lead(whatsapp="https://wa.me/5585999998888", telefone="+5585999998888"))
    chaves = [k for k in linha if not k.startswith("_")]
    assert chaves[:8] == ["Chance de venda", "Prioridade", "Nome", "Tipo", "Cidade", "UF", "Preparar", "Protótipo"]
    assert chaves[-4:] == ["Fonte", "CNPJ", "Aberta em", "ID"]
    assert linha["Abrir conversa"].startswith("https://wa.me/5585999998888?text=Ol%C3%A1")

def test_pontuar_nao_conferido():
    nota, motivos = calcular_chance({}, "Restaurante", "Não conferido", "+558532221111", "", "", "", "Mensagem")
    assert "site não conferido (procure no Google)" in motivos

def test_planilha_ida_e_volta(tmp_path, linhas_exemplo):
    caminho = gerar_planilha(linhas_exemplo, [], {"Data": "2026-10-24"}, tmp_path / "leads.xlsx")
    wb = openpyxl.load_workbook(caminho)
    assert wb.sheetnames == ["Abordar", "Resumo", "Rodada"]
    ws = wb["Abordar"]
    assert "Leads" in ws.tables
    assert ws.data_validations.dataValidation          # lista suspensa existe
    # usuário preenche, apaga a coluna Observações e uma linha fica sem ID
    cab = [c.value for c in ws[1]]
    ws.cell(row=2, column=cab.index("Status contato") + 1, value="Fechado")
    ws.delete_cols(cab.index("Observações") + 1)
    ws.cell(row=3, column=cab.index("ID") + 1, value=None)
    wb.save(caminho)
    lidas = ler_status(caminho)
    assert lidas[0]["Status contato"] == "Fechado" and "Observações" not in lidas[0]
    assert len(lidas) == len(linhas_exemplo) - 1

def test_permission_error_salva_com_sufixo(tmp_path, linhas_exemplo, monkeypatch):
    original = openpyxl.Workbook.save
    def save(self, f):
        if str(f).endswith("leads.xlsx"):
            raise PermissionError
        original(self, f)
    monkeypatch.setattr(openpyxl.Workbook, "save", save)
    assert gerar_planilha(linhas_exemplo, [], {}, tmp_path / "leads.xlsx").name == "leads_2.xlsx"

def test_formato_antigo(tmp_path):
    wb = openpyxl.Workbook(); wb.active.title = "Leads"; wb.active.append(["Nome", "Cidade"]); wb.save(tmp_path / "v.xlsx")
    with pytest.raises(ValueError, match="formato antigo"):
        ler_status(tmp_path / "v.xlsx")
```

- [ ] **Step 2:** rodar → FAIL. **Step 3:** implementar. **Step 4:** `python -m pytest -v` → PASS
  (inclusive os 5 testes de não-regressão da Tarefa 1).
- [ ] **Step 5:** `git add -A; git commit -m "feat: planilha com abas, tabela, links e lista de status"`

---

### Task 7: Verificação de sites em paralelo + CLI de ponta a ponta

**Files:**
- Create: `prospector/sites.py`, `prospector/cli.py`, `tests/test_sites.py`, `tests/test_cli.py`, `README.md`
- Modify: `buscar_leads.py` (vira 3 linhas), `prospector/config.py` (`UFS_PADRAO = ["CE"]`,
  `MAX_MUNICIPIOS = 40`, `REVARRER_DIAS = 90`, `LIMITE_EXPORTAR = 300`,
  `LIMITE_SEM_CONTATO = 100`, `PASTA_SAIDA = "."`, `PASTA_DADOS = "dados"`)

**Interfaces:**
- Consumes: tudo das Tarefas 1-6.
- Produces:
  - `sites.site_no_ar(url) -> bool` (movida sem mudança) e
    `sites.verificar_sites(leads: list[Lead], workers: int = 16) -> int` — só os
    `status_site == "A verificar"`, em `ThreadPoolExecutor`, com barra `tqdm`; muda para
    `"Tem site"`/`"Site fora do ar"`; devolve quantos verificou.
  - `cli.main(argv: list[str] | None = None) -> int`. Subcomandos (sem subcomando = `buscar`):
    - `buscar [--uf CE RN | --uf todos] [--cidade "Gramado/RS" ...] [--min-pop N]
      [--max-municipios N] [--revarrer-dias N] [--ordem populacao|distancia] [--limite N]
      [--incluir-sem-contato] [--sem-verificar-sites] [--tipos "Pousada/Hotel" ...] [--saida PASTA]`
    - `sincronizar [--saida PASTA]` — só passo 1 abaixo.
    - `cnpj [--mes AAAA-MM] [--manter-zips]` — Tarefa 8.

**Fluxo de `buscar` (nesta ordem):**
1. `conn = historico.abrir(dados/prospector.db)`. Para cada `leads_*.xlsx` em `--saida` ainda
   não em `arquivos_importados`: tenta `ler_status` → `atualizar_status`; se `ValueError("formato
   antigo")` → `ler_legado` → `importar_legado` e registra em `arquivos_importados`. Planilhas
   novas são relidas sempre (o usuário continua editando). Qualquer outra exceção ao abrir
   (arquivo aberto/corrompido) → `print("  ! Não consegui ler <arquivo>: <erro>")` e segue.
2. Municípios: `--cidade` (via `achar_cidade`) ou `listar_municipios(--uf)`; filtra `--min-pop`;
   ordena (população desc. ou `distancia_km` asc.); remove `municipios_varridos(conn, "osm",
   agora - revarrer_dias)` (com `--revarrer-dias 0` não remove nenhum); pega os `--max-municipios` primeiros. Guarda quantos faltaram.
3. Para cada município (barra `tqdm`): `osm.buscar_municipio`; `None` → avisa e **não** marca;
   senão (e se `dados/cnpj.db` existir, `cnpj.cruzar` — Tarefa 9) → `salvar_leads` →
   `marcar_varrido` → `time.sleep(2)`.
4. `pend = pendentes(conn)`, filtrado por `--tipos`; sem `--sem-verificar-sites`:
   `verificar_sites(pend)` e `salvar_leads(pend)`.
5. `linhas = [pontuar(l) for l in pend]`, ordena por (`Chance de venda`, `Valor alvo (R$)`) desc.;
   `abordar` = com contato, até `--limite`; `definir_entregas(abordar)`; `pesquisar` = sem contato,
   até `LIMITE_SEM_CONTATO`, só com `--incluir-sem-contato` (senão continuam na fila).
6. Sem nada para exportar → imprime `"Nenhum lead novo para exportar."` e devolve 0 sem criar arquivo.
7. `rodada = nova_rodada(...)`; `caminho = gerar_planilha(..., saida / f"leads_{agora:%Y-%m-%d_%H%M%S}.xlsx")`;
   **só depois** `marcar_exportados(conn, ids, rodada, agora)`.
8. Imprime: municípios varridos / falharam / faltam, leads novos, exportados, fila restante e o caminho.

- [ ] **Step 1: Testes falhando**

```python
# tests/test_sites.py
def test_verifica_so_a_verificar(monkeypatch, fazer_lead):
    monkeypatch.setattr(sites, "site_no_ar", lambda url: url == "https://ok.com")
    leads = [fazer_lead(id="a", site="https://ok.com", status_site="A verificar"),
             fazer_lead(id="b", site="https://off.com", status_site="A verificar"),
             fazer_lead(id="c", status_site="Sem site")]
    assert verificar_sites(leads) == 2
    assert [l.status_site for l in leads] == ["Tem site", "Site fora do ar", "Sem site"]

# tests/test_cli.py — ibge.listar_municipios, osm.buscar_municipio e sites.site_no_ar
# substituídos por fakes; PASTA_DADOS e --saida em tmp_path; time.sleep anulado.
def test_segunda_rodada_nao_repete(ambiente):
    assert main(["buscar", "--uf", "CE", "--saida", str(ambiente.saida)]) == 0
    primeira = ler_ids(ambiente.unica_planilha())
    assert primeira                                  # exportou algo
    ambiente.osm_devolve_os_mesmos_mais_um_novo()
    main(["buscar", "--uf", "CE", "--revarrer-dias", "0", "--saida", str(ambiente.saida)])
    segunda = ler_ids(ambiente.planilha_mais_recente())
    assert set(segunda) == {"osm:node/999"}

def test_falha_overpass_nao_marca_varrido(ambiente):
    ambiente.osm_falha_em("2304400")
    main(["buscar", "--uf", "CE", "--saida", str(ambiente.saida)])
    assert "2304400" not in municipios_varridos(ambiente.conn(), "osm", "2000-01-01T00:00:00")

def test_limite_deixa_resto_na_fila(ambiente):
    ambiente.osm_devolve_n_leads_com_contato(10)
    main(["buscar", "--uf", "CE", "--limite", "4", "--saida", str(ambiente.saida)])
    main(["buscar", "--uf", "CE", "--limite", "4", "--saida", str(ambiente.saida)])
    assert len(ler_ids(ambiente.planilha_mais_recente())) == 4
    assert ambiente.chamadas_osm == 1 * ambiente.n_municipios   # 2ª rodada não consultou de novo

def test_status_da_planilha_volta_e_bloqueia(ambiente):
    main(["buscar", "--uf", "CE", "--saida", str(ambiente.saida)])
    ambiente.preencher_status(ambiente.unica_planilha(), linha=1, status="Não contatar")
    main(["sincronizar", "--saida", str(ambiente.saida)])
    assert ambiente.lead_bloqueado(linha=1)

def test_planilha_antiga_sem_id_e_importada_como_legado(ambiente):
    ambiente.copiar_planilha_antiga_com(nome="Pousada Sol", cidade="Cumbuco - CE", telefone="(85) 3222-1111")
    ambiente.osm_devolve(nome="Pousada Sol", uf="CE", telefone="+558532221111")
    main(["buscar", "--uf", "CE", "--saida", str(ambiente.saida)])
    assert "Pousada Sol" not in ambiente.nomes_exportados()

def test_falha_ao_salvar_nao_marca_exportado(ambiente, monkeypatch):
    monkeypatch.setattr(cli, "gerar_planilha", lambda *a, **k: (_ for _ in ()).throw(OSError("disco cheio")))
    with pytest.raises(OSError):
        main(["buscar", "--uf", "CE", "--saida", str(ambiente.saida)])
    assert pendentes(ambiente.conn())               # continuam na fila

def test_planilha_ilegivel_nao_para_rodada(ambiente):
    (ambiente.saida / "leads_quebrada.xlsx").write_bytes(b"isto nao e um xlsx")
    assert main(["buscar", "--uf", "CE", "--saida", str(ambiente.saida)]) == 0
```

(`ambiente` = fixture em `test_cli.py` que monta os fakes; helpers dela ficam no próprio arquivo.)

- [ ] **Step 2:** rodar → FAIL. **Step 3:** implementar `sites.py`, `cli.py`, reduzir `buscar_leads.py`.
- [ ] **Step 4:** `python -m pytest -v` → PASS.
- [ ] **Step 5: Teste real (com internet)** —
  `python buscar_leads.py buscar --cidade "Gramado/RS" --limite 30`
  Esperado: cria `leads_AAAA-MM-DD_HHMMSS.xlsx` com abas Abordar/Resumo/Rodada e imprime o
  resumo; e a planilha antiga `leads_2026-10-24_0616.xlsx` aparece como importada (legado).
  Rodar o mesmo comando de novo → `"Nenhum lead novo para exportar."` (ou só leads da fila).
- [ ] **Step 6: README.md** — instalação, os comandos acima com exemplos (`--uf todos
  --max-municipios 50`, `--cidade`, `sincronizar`), como funciona o "não repetir", o que cada aba
  significa e que "Sem interesse"/"Não contatar" bloqueiam o lead.
- [ ] **Step 7:** `git add -A; git commit -m "feat: CLI nacional com rodadas, fila e sincronização"`

---

### Task 8: Base de CNPJ da Receita (comando `cnpj`)

**Files:**
- Create: `prospector/cnpj.py`, `tests/test_cnpj.py`
- Modify: `prospector/config.py`, `prospector/cli.py` (subcomando `cnpj`)

**Interfaces:**
- Consumes: `Estab`, `Municipio`, `ibge.listar_municipios(["todos"], ...)`, `texto.*`.
- Produces:
  - `config.RECEITA_WEBDAV = "https://arquivos.receitafederal.gov.br/public.php/webdav/"`,
    `config.RECEITA_TOKEN = "YggdBLfdninEJX9"` (usuário da autenticação básica, senha vazia).
  - `config.CNAE_TIPOS = {"5510801": "Pousada/Hotel", "5510802": "Pousada/Hotel",
    "5590601": "Pousada/Hotel", "5590603": "Pousada/Hotel", "5590699": "Pousada/Hotel",
    "5611201": "Restaurante", "5611203": "Bar/Café", "5611204": "Bar/Café", "5611205": "Bar/Café",
    "7911200": "Agência/Passeio", "7912100": "Agência/Passeio", "7990200": "Agência/Passeio",
    "8591100": "Kitesurf/Esporte", "7721700": "Kitesurf/Esporte", "4781400": "Loja de roupa"}`
    — CNAEs `8591100`/`7721700` só entram se o nome casar `r"kite|surf|wind|sup\b|vela"`.
  - `mes_mais_recente() -> str` — `PROPFIND` (Depth 1) na raiz; maior pasta `AAAA-MM`.
  - `baixar(mes: str, destino: Path) -> list[Path]` — `Municipios.zip` e
    `Estabelecimentos0..9.zip`, em streaming (`iter_content`, 1 MB), barra `tqdm`; pula arquivo
    já baixado com o mesmo tamanho (`Content-Length`).
  - `mapa_municipios(caminho_zip: Path, municipios: list[Municipio]) -> dict[tuple[str, str], str]`
    — chave `(codigo_receita, uf)` → código IBGE, montada casando `normalizar_nome` do nome da
    Receita com o do IBGE **dentro de cada UF**. Como `Municipios.csv` não tem UF, o mapa é
    construído para cada UF que tenha aquele nome. Imprime quantos não casaram.
  - `linha_para_estab(campos: list[str], mapa: dict) -> Estab | None` — `None` se situação ≠ `"02"`,
    CNAE principal fora de `CNAE_TIPOS`, nome fantasia vazio, município sem mapa, ou regra do
    kitesurf. Telefone = `normalizar_telefone(campos[22], campos[21])`, idem tel2 (23, 24);
    abertura `AAAAMMDD` → `AAAA-MM-DD`; e-mail em minúsculas; logradouro = 13+14+15 com espaços.
  - `construir_base(zips: list[Path], caminho_db: Path, mapa: dict) -> int` — lê cada zip com
    `zipfile` + `io.TextIOWrapper(encoding="latin-1", newline="")` + `csv.reader(delimiter=";")`,
    sem extrair no disco; grava em tabela temporária e no fim troca pela definitiva
    `estab(cnpj PK, nome, cnae, tipo, municipio_ibge, uf, logradouro, bairro, cep, telefone,
    telefone2, email, abertura)` com índice em `municipio_ibge` (base antiga continua válida se
    o processo for interrompido). Devolve nº de linhas.
  - `estabs_do_municipio(caminho_db: Path, ibge: str) -> list[Estab]`
  - Subcomando `cnpj`: `mes_mais_recente()` (ou `--mes`) → `baixar` em `dados/receita/{mes}` →
    `construir_base` em `dados/cnpj.db` → apaga os zips salvo `--manter-zips`. Avisa no início:
    "Vai baixar ~5,5 GB e levar de 30 a 90 minutos."

- [ ] **Step 1: Testes falhando** — criar no teste um zip com `Estabelecimentos.csv` de 4 linhas
(uma ativa de hotel em Fortaleza com `;` dentro das aspas do complemento, uma baixada `"08"`,
uma de CNAE fora da lista, uma sem nome fantasia) e um `Municipios.csv` com `"1389";"FORTALEZA"`.

```python
def test_mapa_por_uf(zip_municipios, muns):          # muns: Fortaleza/CE 2304400
    assert mapa_municipios(zip_municipios, muns)[("1389", "CE")] == "2304400"

def test_construir_base_filtra(zip_estabs, mapa, tmp_path):
    assert construir_base([zip_estabs], tmp_path / "cnpj.db", mapa) == 1
    e = estabs_do_municipio(tmp_path / "cnpj.db", "2304400")[0]
    assert (e.tipo, e.telefone, e.abertura, e.email) == ("Pousada/Hotel", "+5585988776655", "2025-11-03", "contato@sol.com")

def test_kitesurf_so_com_nome(mapa):
    # linha_estab_exemplo(**campos) -> list[str] de 30 campos (helper no próprio arquivo)
    assert linha_para_estab(linha_estab_exemplo(cnae="8591100", nome="ACADEMIA FORCA"), mapa) is None
    assert linha_para_estab(linha_estab_exemplo(cnae="8591100", nome="CUMBUCO KITE SCHOOL"), mapa).tipo == "Kitesurf/Esporte"

def test_mes_mais_recente(monkeypatch):
    responder_propfind(monkeypatch, ["2026-08/", "2026-10/", "2026-09/", "cnpj.tar.gz"])
    assert mes_mais_recente() == "2026-10"
```

- [ ] **Step 2:** rodar → FAIL. **Step 3:** implementar. **Step 4:** `python -m pytest -v` → PASS.
- [ ] **Step 5: Teste real (opcional, demorado)** — `python buscar_leads.py cnpj`; ao fim,
  `python -c "import sqlite3;print(sqlite3.connect('dados/cnpj.db').execute('select count(*) from estab').fetchone())"`
  deve mostrar centenas de milhares de linhas.
- [ ] **Step 6:** `git add -A; git commit -m "feat: base aberta de CNPJ da Receita"`

---

### Task 9: Cruzar OSM × Receita e bônus de empresa nova

**Files:**
- Modify: `prospector/cnpj.py` (adicionar `cruzar`), `prospector/pontuacao.py`, `prospector/cli.py`
  (passo 3 do fluxo), `prospector/config.py` (`MESES_EMPRESA_NOVA = 18`, `BONUS_EMPRESA_NOVA = 8`),
  `README.md`, `tests/test_cnpj.py`, `tests/test_pontuacao.py`

**Interfaces:**
- Consumes: `Lead`, `Estab`, `Municipio`, `texto.nucleo_nome`, `rapidfuzz.fuzz.token_sort_ratio`.
- Produces:
  - `cnpj.cruzar(leads: list[Lead], estabs: list[Estab], mun: Municipio) -> list[Lead]` —
    devolve os leads OSM (enriquecidos quando casam) **mais** um `Lead` novo por estab sem par.
    Casamento: mesmo telefone E.164 **ou** (`nucleo_nome` de ambos com ≥ 4 caracteres e
    `token_sort_ratio ≥ 88`); cada estab casa com no máximo um lead (o de maior razão).
    Lead casado: preenche `telefone` (tel1, senão tel2) e `email` só se vazios — e então
    `whatsapp = link_whatsapp(telefone)` —, `cnpj`, `abertura`,
    `fonte="OSM+Receita"`. Lead novo: `id=f"cnpj:{cnpj}"`, `fonte="Receita"`, nome em
    título (`str.title()`), lat/lng = centroide do município, `tags={"addr:street": logradouro}`
    se houver, `status_site="Não conferido"`, WhatsApp via `link_whatsapp` (tel1, senão tel2).
  - `calcular_chance(..., abertura: str = "", hoje: date | None = None)` — se `abertura` está a
    até `MESES_EMPRESA_NOVA` meses de `hoje`: `+BONUS_EMPRESA_NOVA` (antes das penalidades) e
    motivo `"empresa nova (aberta há menos de 18 meses)"`. `pontuar` repassa `lead.abertura`.

- [ ] **Step 1: Testes falhando**

```python
def test_casa_por_nome(fazer_lead, fazer_estab, mun_fortaleza):
    leads = cruzar([fazer_lead(id="osm:node/1", nome="Pousada Sol Nascente", telefone="")],
                   [fazer_estab(nome="POUSADA SOL NASCENTE LTDA", telefone="+5585988776655")], mun_fortaleza)
    assert len(leads) == 1
    assert leads[0].fonte == "OSM+Receita" and leads[0].telefone == "+5585988776655"
    assert leads[0].whatsapp == "https://wa.me/5585988776655"

def test_nome_generico_nao_casa(fazer_lead, fazer_estab, mun_fortaleza):
    leads = cruzar([fazer_lead(id="osm:node/1", nome="Restaurante", telefone="")],
                   [fazer_estab(nome="RESTAURANTE DO ZE", telefone="+558532221111")], mun_fortaleza)
    assert len(leads) == 2 and {l.fonte for l in leads} == {"OSM", "Receita"}

def test_casa_por_telefone_mesmo_com_nome_diferente(fazer_lead, fazer_estab, mun_fortaleza):
    leads = cruzar([fazer_lead(id="osm:node/1", nome="Sol Hostel", telefone="+558532221111")],
                   [fazer_estab(nome="ABC HOSPEDAGEM", telefone="+558532221111")], mun_fortaleza)
    assert len(leads) == 1 and leads[0].cnpj

def test_nao_sobrescreve_contato_do_osm(fazer_lead, fazer_estab, mun_fortaleza):
    l = cruzar([fazer_lead(nome="Pousada Sol Nascente", telefone="+5585999998888")],
               [fazer_estab(nome="POUSADA SOL NASCENTE", telefone="+558532221111")], mun_fortaleza)[0]
    assert l.telefone == "+5585999998888"

def test_lead_so_da_receita(fazer_estab, mun_fortaleza):
    l = cruzar([], [fazer_estab(cnpj="12345678000190", nome="CAFE DA PRACA")], mun_fortaleza)[0]
    assert (l.id, l.fonte, l.nome, l.status_site) == ("cnpj:12345678000190", "Receita", "Cafe Da Praca", "Não conferido")
    assert (l.lat, l.lng) == (mun_fortaleza.lat, mun_fortaleza.lng)

def test_bonus_empresa_nova():
    args = ({}, "Restaurante", "Sem site", "+558532221111", "", "", "", "Mensagem")
    sem, _ = calcular_chance(*args)
    com, motivos = calcular_chance(*args, abertura="2026-01-10", hoje=date(2026, 10, 24))
    velha, _ = calcular_chance(*args, abertura="2020-01-10", hoje=date(2026, 10, 24))
    assert com == sem + 8 and velha == sem
    assert "empresa nova (aberta há menos de 18 meses)" in motivos
```

(`fazer_estab` vai para `tests/conftest.py`, com padrões coerentes com `fazer_lead`.)

- [ ] **Step 2:** rodar → FAIL. **Step 3:** implementar e ligar no passo 3 do `cli.buscar`
  (só quando `dados/cnpj.db` existir). **Step 4:** `python -m pytest -v` → tudo PASS, inclusive
  os testes de não-regressão da Tarefa 1 (o bônus é opcional e não muda os valores antigos).
- [ ] **Step 5: Teste real** (com a base da Tarefa 8) —
  `python buscar_leads.py buscar --cidade "Jijoca de Jericoacoara/CE" --revarrer-dias 0 --limite 50`
  Esperado: aparecem leads com `Fonte` = `OSM+Receita` e `Receita`; percentual com telefone bem
  acima dos 13% da planilha antiga.
- [ ] **Step 6:** README: seção "Base da Receita (opcional, recomendada)" com o comando mensal.
- [ ] **Step 7:** `git add -A; git commit -m "feat: cruzamento OSM x Receita e bônus de empresa nova"`
