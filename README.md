# Prospector de Leads

Ferramenta gratuita para encontrar empresas que precisam de um site (pousadas, hotéis, restaurantes, bares, agências de passeio, escolas de kitesurf/esporte e lojas de roupa) em qualquer cidade ou estado do Brasil.

Não precisa de chave de API, cadastro nem cartão de crédito.

---

## 1. Instalação

Abra o PowerShell na pasta do projeto e instale as bibliotecas necessárias:

```powershell
python -m pip install -r requirements.txt
```

---

## 2. Como usar

### Busca padrão (Ceará, até 40 municípios por rodada)
```powershell
python buscar_leads.py
```

### Buscar em estados específicos ou no Brasil todo
```powershell
python buscar_leads.py buscar --uf CE RN
python buscar_leads.py buscar --uf todos --max-municipios 50
```

### Buscar em cidades escolhidas
```powershell
python buscar_leads.py buscar --cidade "Gramado/RS" "Canela/RS" --limite 100
```

### Filtrar por porte da cidade, distância ou tipo de negócio
```powershell
python buscar_leads.py buscar --uf SP --min-pop 50000 --ordem populacao
python buscar_leads.py buscar --uf CE --ordem distancia --tipos "Pousada/Hotel" "Restaurante"
```

### Sincronizar a planilha sem fazer nova busca
Se você preencheu o andamento das vendas na planilha e quer apenas salvar no banco local:
```powershell
python buscar_leads.py sincronizar
```

### Base da Receita (opcional, recomendada)
Recomenda-se rodar uma vez por mês para baixar os dados abertos de CNPJ da Receita Federal (~5,5 GB, leva de 30 a 90 minutos) e atualizar o banco local `dados/cnpj.db`:
```powershell
python buscar_leads.py cnpj
python buscar_leads.py cnpj --mes 2026-10 --manter-zips
```
O que muda nas buscas quando `dados/cnpj.db` está presente:
- **Mais telefones e e-mails:** empresas do mapa (OSM) que casam por telefone ou nome ganham o telefone, WhatsApp, e-mail, CNPJ e data de abertura da Receita (`Fonte: OSM+Receita`).
- **Empresas que não estão no mapa:** estabelecimentos ativos dos nichos atendidos que só existem na Receita entram na fila (`Fonte: Receita`).
- **Bônus de empresa nova:** empresas abertas há menos de 18 meses ganham pontos extras na chance de venda.
- **Status do site:** leads que vêm só da Receita saem com **`Site: Não conferido`** (pois a Receita não informa URL de site).

---

## 3. Como funciona o "Não repetir leads" e a Fila

1. **Histórico automático (`dados/prospector.db`):** Todo estabelecimento encontrado e toda planilha gerada ficam registrados no seu computador.
2. **Sem repetição:** Uma empresa que já saiu em uma planilha **nunca mais sai de novo** nas próximas rodadas.
3. **Planilhas antigas:** Na primeira vez que você rodar, o programa lê automaticamente suas planilhas antigas (`leads_*.xlsx`) e marca como já exportadas as empresas que tinham contato.
4. **Fila inteligente:** Se uma rodada encontrar 800 empresas com contato e o seu `--limite` for 300, as 300 melhores saem na planilha de hoje e as outras 500 ficam guardadas na fila para as próximas rodadas — sem precisar consultar a internet de novo.
5. **Continue de onde parou:** Cada cidade é salva assim que termina. Se a internet cair ou você apertar `Ctrl+C`, basta rodar o comando novamente para continuar das próximas cidades.

---

## 4. O que cada aba da planilha significa

A planilha gerada (`leads_AAAA-MM-DD_HHMMSS.xlsx`) vem organizada em abas:

- **Abordar:** Empresas que já têm telefone, WhatsApp, e-mail ou rede social, ordenadas da maior chance de venda para a menor.
  - Clique em **Abrir conversa** para abrir o WhatsApp já com uma mensagem personalizada para aquele nicho.
  - Clique em **Ver no Google Maps** ou **URL atual** para abrir direto no navegador.
  -Veja em **Preparar** (`Site final`, `Protótipo` ou `Nada agora`) e os valores sugeridos (**Oferta inicial**, **Valor alvo** e **Mínimo**).
- **Pesquisar contato** *(aparece quando você usa `--incluir-sem-contato`)*: Empresas com bom perfil que não tinham telefone cadastrado no mapa, com link direto para você procurar no Google Maps.
- **Resumo:** Quantidade de leads Quentes, Mornos e Frios, horas estimadas de trabalho, soma dos valores alvo e as cidades com mais oportunidades.
- **Rodada:** Registro da data, comando executado, quantos municípios foram varridos, quantos ainda faltam e quantos leads continuam na fila.

---

## 5. Acompanhamento de vendas e bloqueio de leads

Na aba **Abordar**, você tem três colunas para preencher durante o seu trabalho comercial:

- **Status contato** (lista suspensa):
  - `Mensagem enviada`
  - `Respondeu`
  - `Reunião marcada`
  - `Proposta enviada`
  - `Fechado`
  - `Sem interesse`
  - `Não contatar`
- **Valor fechado (R$):** quanto o cliente fechou.
- **Observações:** anotações livres.

Sempre que você rodar uma nova busca (ou `python buscar_leads.py sincronizar`), o programa lê automaticamente suas planilhas salvas na pasta e guarda essas informações no banco.

> **Importante:** Marcar um lead como **`Sem interesse`** ou **`Não contatar`** bloqueia essa empresa permanentemente no banco de dados para que ela nunca mais volte.

---

## 6. App no celular (GitHub Actions + GitHub Pages)

O Prospector também roda sozinho no GitHub e publica um app que você instala no celular.
Tudo é gratuito para repositório público.

### Como funciona

- **Busca automática:** o workflow `Buscar leads` roda toda segunda às 06:17 (horário de Fortaleza)
  e sempre que você pedir. Ele usa o mesmo `buscar_leads.py`, com histórico, fila e "não repetir".
- **Histórico:** o banco `prospector.db` fica guardado no ramo `dados` do repositório
  (o ramo é criado sozinho na primeira execução).
- **App:** a pasta `app/` é publicada no GitHub Pages junto com o `leads.json` gerado na busca.
  O endereço fica `https://SEU-USUARIO.github.io/prospectoror-core/`.
- **Seu andamento** (status, valor fechado, nota do Google e observações) fica salvo no celular.
  Use **Mais → Salvar backup** de vez em quando.
- A base da Receita (`cnpj`) não roda no GitHub (5,5 GB). As buscas lá usam só o OpenStreetMap.

### Ativar (uma vez)

1. Envie estes arquivos para o GitHub (commit + push no ramo `main`).
2. No GitHub, abra **Settings → Pages** e, em *Build and deployment → Source*, escolha **GitHub Actions**.
3. Em **Settings → Actions → General → Workflow permissions**, marque **Read and write permissions** e salve.
4. Opcional, para não receber de novo os leads que você já tem no PC: copie `dados/prospector.db`
   para uma pasta `semente/` na raiz do projeto e faça commit **antes** da primeira busca.
   Atenção: o repositório é público, então esse arquivo (com suas anotações das planilhas) fica visível.
5. Abra **Actions → Buscar leads → Run workflow** e confirme. A primeira rodada leva de 10 a 60 minutos.
6. Quando terminar, abra o endereço do app no celular e instale:
   - **Android (Chrome):** menu ⋮ → *Adicionar à tela inicial* / *Instalar app*.
   - **iPhone (Safari):** Compartilhar → *Adicionar à Tela de Início*.

### Buscar outras regiões pelo celular

No app, toque em **Mais → Buscar agora no GitHub**, depois em **Run workflow**. Dá para escolher:
- **uf:** `CE RN` ou `todos`
- **cidades:** `Gramado/RS, Canela/RS` (se preenchido, ignora a UF)
- **max_municipios** e **limite**
- **tipos:** `Pousada/Hotel, Restaurante`

### Gerar o JSON no PC

O mesmo arquivo do app pode ser gerado localmente:
```powershell
python buscar_leads.py buscar --uf CE --json leads.json
```
