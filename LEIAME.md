# Monitor de Licitações INPAV · Prefeituras de MT

Busca todo dia (às 06h e às 15h, horário de Cuiabá) as licitações das prefeituras de Mato Grosso
ligadas à atividade da INPAV: pavimentação, drenagem, saneamento (estações elevatórias, adutoras,
captação de água, redes de água e esgoto) e obras civis/estradas. Cobre licitações **presenciais e eletrônicas**.

O resultado aparece num **painel web** (abre no celular ou no computador) e numa **planilha Excel**.

## De onde vêm os dados

| Fonte | O que cobre |
|---|---|
| **PNCP** (Portal Nacional de Contratações Públicas) | Todas as prefeituras que já publicam pela Lei 14.133: pregões, concorrências, dispensas, presenciais e eletrônicos |
| **Querido Diário** | Diários oficiais municipais (só parte dos municípios de MT); serve de complemento |

> Atenção: municípios com até 20 mil habitantes têm até abril/2027 para entrar no PNCP. Alguns ainda publicam
> só no **Jornal Oficial da AMM** (diariomunicipal.org/mt/amm). O painel tem um link para ele no rodapé.

---

## Instalação (uma vez só, cerca de 10 minutos, grátis)

1. **Crie uma conta no GitHub** em https://github.com/signup (se ainda não tiver).
2. **Crie um repositório novo**: botão **New** → nome `licitacoes-inpav` → marque **Public** → **Create repository**.
   (Precisa ser público para o painel funcionar de graça. Ele mostra só dados públicos de licitações.)
3. **Envie os arquivos**: na página do repositório clique em **uploading an existing file**, arraste
   **todo o conteúdo** desta pasta (incluindo a pasta `.github`) e clique em **Commit changes**.
   - Se a pasta `.github` não subir pelo navegador (ela é oculta no Windows), crie o arquivo à mão:
     **Add file → Create new file**, nome `.github/workflows/coletar.yml`, e cole o conteúdo do arquivo.
4. **Libere a automação**: aba **Settings → Actions → General** → em *Workflow permissions* marque
   **Read and write permissions** → **Save**.
5. **Ligue o painel**: **Settings → Pages** → *Source*: **Deploy from a branch** → Branch **main**, pasta **/docs** → **Save**.
6. **Rode a primeira coleta**: aba **Actions** → **Coletar licitações MT** → **Run workflow**. Leva poucos minutos.
7. **Abra o painel** no endereço que aparece em Settings → Pages, algo como
   `https://SEU-USUARIO.github.io/licitacoes-inpav/`. Salve nos favoritos do celular.

Daí em diante ele atualiza sozinho duas vezes por dia, mesmo com o computador desligado.

## Usando o painel

- **Filtros**: busca por texto, município, forma (Presencial / Eletrônica), área, e "só novas (48h)".
- **Cores**: borda laranja = encerra em até 7 dias; verde = mais prazo.
- **Ver no PNCP**: abre o edital e os arquivos. **Sistema de disputa** abre a plataforma onde ocorre o pregão eletrônico.
- **Planilha completa (Excel)**: todas as licitações com links clicáveis. **Baixar filtradas (CSV)**: só o que está na tela.

## Ajustando o que ele procura

Edite o `config.json` direto no GitHub (clique no arquivo → ícone de lápis):

- `grupos` → palavras procuradas no objeto da licitação, por área. Pode acrescentar termos.
- `exclusoes` → descarta itens que só casaram com "Obras civis" e têm esses termos (ex.: "reforma de pneus").
- `incluir_estado: true` → passa a mostrar também órgãos estaduais de MT (ex.: SINFRA).
- `modalidades` → tipos de contratação consultados no PNCP.

## Rodar no próprio computador (opcional)

```
pip install -r requirements.txt
python coletor.py
```
Depois abra `docs/index.html` com um servidor local (`python -m http.server -d docs`) e acesse http://localhost:8000.
