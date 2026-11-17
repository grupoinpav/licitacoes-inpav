#!/usr/bin/env python3
"""
Monitor de Licitações INPAV — prefeituras de Mato Grosso.

Fontes:
  1. PNCP (Portal Nacional de Contratações Públicas) — API pública de consulta.
     Todas as prefeituras que já usam a Lei 14.133 publicam lá.
  2. Querido Diário — busca em diários oficiais municipais (complementar;
     cobre só parte dos municípios).

Saídas (pasta docs/dados/):
  licitacoes.json  -> lido pelo painel (docs/index.html)
  licitacoes.xlsx  -> planilha para baixar
  licitacoes.csv   -> planilha simples
"""
import csv
import hashlib
import json
import re
import sys
import time
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent
DADOS = RAIZ / "docs" / "dados"
ARQ_JSON = DADOS / "licitacoes.json"

PNCP = "https://pncp.gov.br/api/consulta/v1"
QD = "https://api.queridodiario.ok.org.br"

SESSAO = requests.Session()
SESSAO.headers.update({"User-Agent": "monitor-licitacoes-inpav/1.0", "Accept": "application/json"})


# ----------------------------------------------------------------- utilidades
def log(*a):
    print(datetime.now().strftime("%H:%M:%S"), *a, flush=True)


def normalizar(txt):
    txt = unicodedata.normalize("NFKD", str(txt or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", txt.lower())


def get_json(url, params, tentativas=4):
    """GET com novas tentativas. Retorna dict, ou None se não houver conteúdo."""
    for n in range(tentativas):
        try:
            r = SESSAO.get(url, params=params, timeout=60)
            if r.status_code == 204 or not r.content:
                return None
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {r.status_code}")
            if r.status_code >= 400:
                log(f"  aviso: HTTP {r.status_code} em {url} {params} -> {r.text[:200]}")
                return None
            return r.json()
        except (requests.RequestException, ValueError) as e:
            espera = 3 * (n + 1)
            log(f"  falha ({e}); tentando de novo em {espera}s")
            time.sleep(espera)
    log(f"  desisti de {url} {params}")
    return None


# ------------------------------------------------------- filtro por palavras
class Filtro:
    def __init__(self, cfg):
        self.grupos = []
        for nome, g in cfg["grupos"].items():
            padroes = []
            for termo in g["termos"]:
                t = re.escape(normalizar(termo))
                fim = r"\b" if len(termo) <= 4 else ""
                padroes.append((termo, re.compile(r"\b" + t + fim)))
            self.grupos.append((nome, bool(g.get("fraco")), padroes))
        self.exclusoes = [re.compile(r"\b" + re.escape(normalizar(t))) for t in cfg.get("exclusoes", [])]

    def avaliar(self, texto):
        """Retorna (categorias, termos) ou None se não for relevante."""
        t = normalizar(texto)
        cats, termos, so_fraco = [], [], True
        for nome, fraco, padroes in self.grupos:
            achou = [termo for termo, p in padroes if p.search(t)]
            if achou:
                cats.append(nome)
                termos += achou
                if not fraco:
                    so_fraco = False
        if not cats:
            return None
        if so_fraco and any(p.search(t) for p in self.exclusoes):
            return None
        return cats, sorted(set(termos))


# --------------------------------------------------------------------- PNCP
def forma_disputa(modalidade, modo):
    m = normalizar(f"{modalidade} {modo}")
    if "presencial" in m:
        return "Presencial"
    if "eletron" in m:
        return "Eletrônica"
    return "Não informado"


def item_pncp(c, cfg):
    org = c.get("orgaoEntidade") or {}
    uni = c.get("unidadeOrgao") or {}
    if (uni.get("ufSigla") or "").upper() != cfg["uf"]:
        return None
    esfera = (org.get("esferaId") or "").upper()
    aceitas = {"M"} if cfg.get("apenas_municipios", True) else {"M", "E", "F", "D", "N"}
    if cfg.get("incluir_estado"):
        aceitas.add("E")
    if esfera and esfera not in aceitas:
        return None

    cnpj, ano, seq = org.get("cnpj"), c.get("anoCompra"), c.get("sequencialCompra")
    modalidade = c.get("modalidadeNome") or ""
    return {
        "id": c.get("numeroControlePNCP") or f"{cnpj}-{ano}-{seq}",
        "fonte": "PNCP",
        "municipio": uni.get("municipioNome") or "",
        "orgao": org.get("razaoSocial") or "",
        "unidade": uni.get("nomeUnidade") or "",
        "esfera": {"M": "Municipal", "E": "Estadual", "F": "Federal"}.get(esfera, esfera),
        "objeto": (c.get("objetoCompra") or "").strip(),
        "info": (c.get("informacaoComplementar") or "").strip(),
        "numero": f"{c.get('numeroCompra') or ''}/{ano or ''}".strip("/"),
        "processo": c.get("processo") or "",
        "modalidade": modalidade,
        "modo_disputa": c.get("modoDisputaNome") or "",
        "forma": forma_disputa(modalidade, c.get("modoDisputaNome")),
        "valor": c.get("valorTotalEstimado"),
        "abertura": c.get("dataAberturaProposta"),
        "encerramento": c.get("dataEncerramentoProposta"),
        "publicacao": c.get("dataPublicacaoPncp"),
        "situacao": c.get("situacaoCompraNome") or "",
        "link": f"https://pncp.gov.br/app/editais/{cnpj}/{ano}/{seq}" if cnpj and ano and seq else "",
        "link_sistema": c.get("linkSistemaOrigem") or "",
    }


def paginar(endpoint, params):
    pagina = 1
    while True:
        dados = get_json(f"{PNCP}/{endpoint}", {**params, "pagina": pagina, "tamanhoPagina": 50})
        if not dados or not dados.get("data"):
            return
        yield from dados["data"]
        if pagina >= int(dados.get("totalPaginas") or 1):
            return
        pagina += 1
        time.sleep(0.4)


def coletar_pncp(cfg, filtro):
    hoje = date.today()
    achados, vistos = {}, 0
    for cod, nome in cfg["modalidades"].items():
        # (a) com recebimento de propostas em aberto
        log(f"PNCP propostas abertas — {nome}")
        for c in paginar("contratacoes/proposta", {
            "dataFinal": (hoje + timedelta(days=cfg["dias_a_frente"])).strftime("%Y%m%d"),
            "codigoModalidadeContratacao": cod, "uf": cfg["uf"]}):
            vistos += 1
            _registrar(c, cfg, filtro, achados)
        # (b) publicadas nos últimos dias (pega também as sem prazo de proposta)
        log(f"PNCP publicadas recentes — {nome}")
        for c in paginar("contratacoes/publicacao", {
            "dataInicial": (hoje - timedelta(days=cfg["dias_retroativos_publicacao"])).strftime("%Y%m%d"),
            "dataFinal": hoje.strftime("%Y%m%d"),
            "codigoModalidadeContratacao": cod, "uf": cfg["uf"]}):
            vistos += 1
            _registrar(c, cfg, filtro, achados)
    log(f"PNCP: {vistos} registros lidos, {len(achados)} relevantes para a INPAV")
    return list(achados.values())


def _registrar(c, cfg, filtro, achados):
    it = item_pncp(c, cfg)
    if not it:
        return
    r = filtro.avaliar(f"{it['objeto']} {it['info']}")
    if not r:
        return
    it["categorias"], it["termos"] = r
    achados[it["id"]] = it


# ------------------------------------------------------------ Querido Diário
def coletar_querido_diario(cfg, filtro):
    try:
        cidades = get_json(f"{QD}/cities", {"city_name": ""}) or {}
        mt = [c["territory_id"] for c in cidades.get("cities", [])
              if c.get("state_code") == cfg["uf"] and str(c.get("territory_id", "")).startswith("51")]
    except Exception as e:  # fonte complementar: nunca derruba a coleta
        log(f"Querido Diário indisponível ({e})")
        return []
    if not mt:
        log("Querido Diário: nenhum município de MT disponível")
        return []
    log(f"Querido Diário: {len(mt)} municípios de {cfg['uf']} cobertos")

    termos_busca = ["pavimentação", "asfáltica", "drenagem", "esgotamento sanitário",
                    "estação elevatória", "adutora", "abastecimento de água", "recapeamento",
                    "terraplenagem", "obras de engenharia"]
    consulta = "(" + " | ".join(f'"{t}"' for t in termos_busca) + ") + (pregão | concorrência | licitação | edital)"
    desde = (date.today() - timedelta(days=cfg["dias_retroativos_publicacao"])).isoformat()
    itens = []
    for i in range(0, len(mt), 40):  # lotes de municípios
        dados = get_json(f"{QD}/gazettes", {
            "territory_ids": mt[i:i + 40], "querystring": consulta,
            "published_since": desde, "excerpt_size": 600, "number_of_excerpts": 5,
            "size": 100, "pre_tags": "", "post_tags": ""}) or {}
        for g in dados.get("gazettes", []):
            for n, trecho in enumerate(g.get("excerpts") or []):
                trecho = re.sub(r"\s+", " ", trecho).strip()
                r = filtro.avaliar(trecho)
                if not r:
                    continue
                itens.append({
                    "id": f"QD-{g.get('territory_id')}-{g.get('date')}-{hashlib.md5(trecho.encode()).hexdigest()[:10]}",
                    "fonte": "Diário Oficial",
                    "municipio": g.get("territory_name") or "",
                    "orgao": f"Prefeitura de {g.get('territory_name')}",
                    "unidade": "", "esfera": "Municipal",
                    "objeto": trecho[:600], "info": "", "numero": "", "processo": "",
                    "modalidade": _modalidade_texto(trecho), "modo_disputa": "",
                    "forma": forma_disputa(trecho, ""),
                    "valor": None, "abertura": None, "encerramento": None,
                    "publicacao": g.get("date"), "situacao": "Publicado em diário",
                    "link": g.get("url") or "", "link_sistema": "",
                    "categorias": r[0], "termos": r[1],
                })
        time.sleep(1)
    log(f"Querido Diário: {len(itens)} trechos relevantes")
    return itens


def _modalidade_texto(t):
    t = normalizar(t)
    for chave, nome in [("pregao eletronico", "Pregão - Eletrônico"), ("pregao presencial", "Pregão - Presencial"),
                        ("concorrencia eletronica", "Concorrência - Eletrônica"),
                        ("concorrencia presencial", "Concorrência - Presencial"),
                        ("tomada de precos", "Tomada de Preços"), ("pregao", "Pregão"),
                        ("concorrencia", "Concorrência"), ("dispensa", "Dispensa")]:
        if chave in t:
            return nome
    return "Aviso em diário oficial"


# ------------------------------------------------------------ juntar e salvar
def mesclar(novos, cfg):
    agora = datetime.now().isoformat(timespec="seconds")
    antigos = {}
    if ARQ_JSON.exists():
        try:
            antigos = {i["id"]: i for i in json.loads(ARQ_JSON.read_text("utf-8")).get("licitacoes", [])}
        except Exception:
            pass
    for it in novos:
        it["visto_em"] = antigos.get(it["id"], {}).get("visto_em", agora)
        antigos[it["id"]] = it

    limite = (date.today() - timedelta(days=cfg["manter_encerradas_por_dias"])).isoformat()
    def manter(i):
        ref = i.get("encerramento") or i.get("abertura") or i.get("publicacao") or i.get("visto_em") or ""
        return ref[:10] >= limite
    lista = [i for i in antigos.values() if manter(i)]
    lista.sort(key=lambda i: (i.get("encerramento") or i.get("abertura") or "9999"))
    return lista


def salvar(lista, fontes):
    DADOS.mkdir(parents=True, exist_ok=True)
    pacote = {"atualizado_em": datetime.now().isoformat(timespec="seconds"),
              "fontes": fontes, "total": len(lista), "licitacoes": lista}
    ARQ_JSON.write_text(json.dumps(pacote, ensure_ascii=False, indent=1), "utf-8")

    colunas = [("Município", "municipio"), ("Órgão", "orgao"), ("Objeto", "objeto"),
               ("Modalidade", "modalidade"), ("Forma", "forma"), ("Valor estimado (R$)", "valor"),
               ("Abertura propostas", "abertura"), ("Encerramento propostas", "encerramento"),
               ("Publicação", "publicacao"), ("Situação", "situacao"), ("Categorias", "categorias"),
               ("Nº", "numero"), ("Fonte", "fonte"), ("Link", "link"), ("Sistema de origem", "link_sistema"),
               ("Encontrado em", "visto_em")]

    def valor(i, k):
        v = i.get(k)
        if isinstance(v, list):
            return ", ".join(v)
        if k in ("abertura", "encerramento", "publicacao", "visto_em") and v:
            try:
                return datetime.fromisoformat(v[:19])
            except ValueError:
                return v
        return v

    with open(DADOS / "licitacoes.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow([c for c, _ in colunas])
        for i in lista:
            w.writerow([valor(i, k).strftime("%d/%m/%Y %H:%M") if isinstance(valor(i, k), datetime)
                        else valor(i, k) for _, k in colunas])

    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError:
        log("openpyxl ausente — planilha .xlsx não gerada")
        return
    wb = Workbook()
    ws = wb.active
    ws.title = "Licitações MT"
    ws.append([c for c, _ in colunas])
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F3A5F")
        c.alignment = Alignment(vertical="center", wrap_text=True)
    for i in lista:
        ws.append([valor(i, k) for _, k in colunas])
    larguras = [18, 30, 60, 22, 13, 16, 17, 17, 17, 16, 24, 10, 12, 40, 40, 17]
    for n, w in enumerate(larguras, 1):
        ws.column_dimensions[get_column_letter(n)].width = w
    for row in ws.iter_rows(min_row=2):
        row[2].alignment = Alignment(wrap_text=True, vertical="top")
        row[5].number_format = '#,##0.00'
        for idx in (6, 7, 8, 15):
            row[idx].number_format = "dd/mm/yyyy hh:mm"
        link = row[13].value
        if link:
            row[13].hyperlink = link
            row[13].font = Font(color="0563C1", underline="single")
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    wb.save(DADOS / "licitacoes.xlsx")


def main():
    cfg = json.loads((RAIZ / "config.json").read_text("utf-8"))
    filtro = Filtro(cfg)
    fontes = {}
    itens = []

    pncp = coletar_pncp(cfg, filtro)
    fontes["PNCP"] = len(pncp)
    itens += pncp

    qd = coletar_querido_diario(cfg, filtro)
    fontes["Diário Oficial (Querido Diário)"] = len(qd)
    itens += qd

    lista = mesclar(itens, cfg)
    salvar(lista, fontes)
    log(f"Pronto: {len(lista)} licitações no painel")
    return 0


if __name__ == "__main__":
    sys.exit(main())
