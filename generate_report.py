#!/usr/bin/env python3
"""
Aquabeat Ads Performance Report Generator
Lê todos os CSVs da pasta e gera relatório HTML completo.
"""

import csv
import io
import json
import re
import os
from pathlib import Path
from datetime import datetime
import pandas as pd

BASE = Path(__file__).parent

# ─── Helpers ───────────────────────────────────────────────────────────────────

def to_float(v):
    """Converte string para float, retorna 0.0 se não for possível."""
    if v is None:
        return 0.0
    s = str(v).strip().replace(' ', '')
    if s in ('', '--', 'N/A', 'nan', 'None'):
        return 0.0
    # remove % sign
    s = s.replace('%', '')
    try:
        return float(s)
    except Exception:
        return 0.0

def fmt_brl(v):
    """Formata número como moeda BRL."""
    try:
        return f"R$ {float(v):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    except Exception:
        return "R$ 0,00"

def fmt_n(v, decimals=0):
    """Formata número com separadores."""
    try:
        if decimals == 0:
            return f"{int(float(v)):,}".replace(',', '.')
        return f"{float(v):,.{decimals}f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    except Exception:
        return "0"

def fmt_pct(v):
    return f"{to_float(v):.2f}%".replace('.', ',')

# ─── META ADS ──────────────────────────────────────────────────────────────────

MONTH_PATTERNS = {
    "Dez/25": ("dez", "2025"),
    "Jan/26": ("jan", "2026"),
    "Fev/26": ("fev", "2026"),
}

def load_meta_month(month_key):
    """Carrega e agrega dados Meta Ads dos 3 accounts para um mês."""
    slug, year = MONTH_PATTERNS[month_key]
    contas = ["CONTA_OFC", "CONTA_ING", "CONTA_INTERNA"]
    result = {
        "investimento": 0.0, "impressoes": 0.0, "alcance": 0.0,
        "cliques": 0.0, "ctr": [], "cpc": [], "cpm": [],
        "resultados": 0.0, "cpl": [], "campaigns": []
    }
    for conta in contas:
        pattern = f"*{conta}-Campanhas*{slug}*{year}*.csv"
        files = list(BASE.glob(pattern))
        if not files:
            # try lowercase
            files = list(BASE.glob(f"*{conta}*{slug}*{year}*.csv"))
        if not files:
            continue
        fpath = files[0]
        try:
            df = pd.read_csv(fpath, encoding='utf-8-sig')
        except Exception:
            df = pd.read_csv(fpath, encoding='latin-1')

        # Totals row = where "Nome da campanha" is NaN/empty
        totals = df[df["Nome da campanha"].isna() | (df["Nome da campanha"].astype(str).str.strip() == "")]
        camps = df[df["Nome da campanha"].notna() & (df["Nome da campanha"].astype(str).str.strip() != "")]

        col_inv = "Valor usado (BRL)"
        col_imp = "Impressões"
        col_alc = "Alcance"
        col_cli = "Cliques (todos)"
        col_ctr = "CTR (todos)"
        col_cpc = "CPC (todos) (BRL)"
        col_cpm = "CPM (custo por 1.000 impressões) (BRL)"
        col_res = "Resultados"
        col_cpl = "Custo por resultados"
        col_camp = "Nome da campanha"

        def get_tot(col):
            if col in totals.columns and not totals.empty:
                return to_float(totals.iloc[0].get(col, 0))
            # fallback: sum camps
            if col in camps.columns:
                return camps[col].apply(to_float).sum()
            return 0.0

        result["investimento"] += get_tot(col_inv)
        result["impressoes"] += get_tot(col_imp)
        result["alcance"] += get_tot(col_alc)
        result["cliques"] += get_tot(col_cli)

        inv = get_tot(col_inv)
        imp = get_tot(col_imp)
        cli = get_tot(col_cli)
        res = get_tot(col_res)

        if inv > 0 and imp > 0:
            result["cpm"].append(inv / imp * 1000)
        if inv > 0 and cli > 0:
            result["cpc"].append(inv / cli)
        if imp > 0 and cli > 0:
            result["ctr"].append(cli / imp * 100)
        if inv > 0 and res > 0:
            result["cpl"].append(inv / res)

        result["resultados"] += res

        # Per-campaign detail
        for _, row in camps.iterrows():
            camp_inv = to_float(row.get(col_inv, 0))
            camp_res = to_float(row.get(col_res, 0))
            camp_cpl = to_float(row.get(col_cpl, 0)) if camp_res > 0 else 0
            result["campaigns"].append({
                "conta": conta.replace("CONTA_", ""),
                "nome": str(row.get(col_camp, "")).strip(),
                "investimento": camp_inv,
                "impressoes": to_float(row.get(col_imp, 0)),
                "alcance": to_float(row.get(col_alc, 0)),
                "resultados": camp_res,
                "cpl": camp_cpl,
                "ctr": to_float(row.get(col_ctr, 0)),
                "cpc": to_float(row.get(col_cpc, 0)),
                "cpm": to_float(row.get(col_cpm, 0)),
            })

    # Compute averages
    result["ctr_avg"] = sum(result["ctr"]) / len(result["ctr"]) if result["ctr"] else 0
    result["cpc_avg"] = sum(result["cpc"]) / len(result["cpc"]) if result["cpc"] else 0
    result["cpm_avg"] = sum(result["cpm"]) / len(result["cpm"]) if result["cpm"] else 0
    result["cpl_avg"] = result["investimento"] / result["resultados"] if result["resultados"] > 0 else 0
    return result


def load_meta_all():
    return {m: load_meta_month(m) for m in MONTH_PATTERNS}


# ─── TIKTOK ADS ────────────────────────────────────────────────────────────────

TIKTOK_MONTH_MAP = {
    "Dez/25": "Dez25",
    "Jan/26": "Jan26",
    "Fev/26": "fev26",
}

def load_tiktok_month(month_key):
    slug = TIKTOK_MONTH_MAP[month_key]
    files = list(BASE.glob(f"Tiktok Ads*{slug}*.csv"))
    result = {
        "investimento": 0.0, "impressoes": 0.0, "alcance": 0.0,
        "resultados": 0.0, "cpl_avg": 0.0, "cpc_avg": 0.0, "cpm_avg": 0.0,
        "campaigns": []
    }
    if not files:
        return result
    try:
        df = pd.read_csv(files[0], encoding='utf-8-sig')
    except Exception:
        df = pd.read_csv(files[0], encoding='latin-1')

    col_custo = "Custo"
    col_imp = "Impressões"
    col_alc = "Alcance"
    col_res = "Resultados"
    col_cpr = "Custo por resultado"
    col_cpc = "CPC (Destino)"
    col_cpm = "CPM"
    col_camp = "Nome da campanha"

    active = df[df[col_custo].apply(to_float) > 0]

    result["investimento"] = active[col_custo].apply(to_float).sum()
    result["impressoes"] = active[col_imp].apply(to_float).sum()
    result["alcance"] = active[col_alc].apply(to_float).sum()
    result["resultados"] = active[col_res].apply(to_float).sum()

    inv = result["investimento"]
    imp = result["impressoes"]
    cli = active["Cliques (Destino)"].apply(to_float).sum() if "Cliques (Destino)" in active.columns else 0
    res = result["resultados"]

    result["cpm_avg"] = inv / imp * 1000 if imp > 0 else 0
    result["cpc_avg"] = inv / cli if cli > 0 else 0
    result["cpl_avg"] = inv / res if res > 0 else 0

    for _, row in active.iterrows():
        result["campaigns"].append({
            "nome": str(row.get(col_camp, "")).strip(),
            "investimento": to_float(row.get(col_custo, 0)),
            "impressoes": to_float(row.get(col_imp, 0)),
            "alcance": to_float(row.get(col_alc, 0)),
            "resultados": to_float(row.get(col_res, 0)),
            "cpl": to_float(row.get(col_cpr, 0)),
            "cpc": to_float(row.get(col_cpc, 0)),
            "cpm": to_float(row.get(col_cpm, 0)),
        })

    return result


def load_tiktok_all():
    return {m: load_tiktok_month(m) for m in MONTH_PATTERNS}


# ─── GOOGLE ADS ────────────────────────────────────────────────────────────────

def load_google_ads():
    """Google Ads - apenas Dezembro 2025 (3 arquivos iguais, usa o primeiro)."""
    files = list(BASE.glob("Relatorio Trafego 2026*.csv"))
    result = {
        "periodo": "Dezembro 2025",
        "investimento": 0.0, "impressoes": 0.0, "cliques": 0.0,
        "cpc_avg": 0.0, "cpm_avg": 0.0, "ctr_avg": 0.0,
        "conversoes": 0.0, "custo_conv": 0.0, "campaigns": []
    }
    if not files:
        return result
    fpath = files[0]
    try:
        df = pd.read_csv(fpath, skiprows=2, encoding='utf-8')
    except Exception:
        df = pd.read_csv(fpath, skiprows=2, encoding='latin-1')

    def clean_val(v):
        s = str(v).strip().replace(',', '').replace(' ', '')
        if s in ('--', '', 'nan', 'None'):
            return 0.0
        try:
            return float(s.replace('%', ''))
        except Exception:
            return 0.0

    for col in ['Cost', 'Impr.', 'Clicks', 'CTR', 'Conversions', 'Cost / conv.', 'Avg. CPC', 'Avg. CPM']:
        if col in df.columns:
            df[col] = df[col].apply(clean_val)

    active = df[df['Cost'] > 0] if 'Cost' in df.columns else df.iloc[0:0]

    result["investimento"] = active['Cost'].sum() if 'Cost' in active.columns else 0
    result["impressoes"] = active['Impr.'].sum() if 'Impr.' in active.columns else 0
    result["cliques"] = active['Clicks'].sum() if 'Clicks' in active.columns else 0
    result["conversoes"] = active['Conversions'].sum() if 'Conversions' in active.columns else 0

    inv = result["investimento"]
    imp = result["impressoes"]
    cli = result["cliques"]
    conv = result["conversoes"]

    result["cpm_avg"] = inv / imp * 1000 if imp > 0 else 0
    result["cpc_avg"] = inv / cli if cli > 0 else 0
    result["ctr_avg"] = cli / imp * 100 if imp > 0 else 0
    result["custo_conv"] = inv / conv if conv > 0 else 0

    # Per-campaign
    if 'Campaign' in active.columns:
        camp_grp = active.groupby('Campaign').agg({
            'Cost': 'sum', 'Impr.': 'sum', 'Clicks': 'sum', 'Conversions': 'sum'
        }).reset_index()
        for _, row in camp_grp.iterrows():
            result["campaigns"].append({
                "nome": str(row['Campaign']),
                "investimento": row['Cost'],
                "impressoes": row['Impr.'],
                "cliques": row['Clicks'],
                "conversoes": row['Conversions'],
            })

    return result


# ─── VENDAS DAYUSE ─────────────────────────────────────────────────────────────

DAYUSE_MONTH_MAP = {
    "Dez/25": "Dez25",
    "Jan/26": "Jan26",
    "Fev/26": "Fev26",
}

def load_dayuse_month(month_key):
    slug = DAYUSE_MONTH_MAP[month_key]
    files = list(BASE.glob(f"Vendas DayUse {slug}.csv"))
    result = {"total_ingressos": 0, "total_receita": 0.0, "ticket_medio": 0.0, "consultores": []}
    if not files:
        return result
    try:
        df = pd.read_csv(files[0], encoding='utf-8-sig', sep=';')
    except Exception:
        df = pd.read_csv(files[0], encoding='latin-1', sep=';')

    df['TotalIngressos'] = df['TotalIngressos'].apply(to_float)
    df['ValorTotalVendido'] = df['ValorTotalVendido'].apply(to_float)
    df['TicketMedio'] = df['TicketMedio'].apply(to_float)

    result["total_ingressos"] = int(df['TotalIngressos'].sum())
    result["total_receita"] = df['ValorTotalVendido'].sum()
    total_ing = result["total_ingressos"]
    result["ticket_medio"] = result["total_receita"] / total_ing if total_ing > 0 else 0

    top = df.nlargest(10, 'ValorTotalVendido')
    for _, row in top.iterrows():
        result["consultores"].append({
            "nome": str(row.get('Consultor', '')).strip(),
            "ingressos": int(to_float(row.get('TotalIngressos', 0))),
            "receita": to_float(row.get('ValorTotalVendido', 0)),
            "ticket": to_float(row.get('TicketMedio', 0)),
        })
    return result


def load_dayuse_all():
    return {m: load_dayuse_month(m) for m in MONTH_PATTERNS}


# ─── VENDAS COTAS ──────────────────────────────────────────────────────────────

COTA_MONTH_MAP = {
    "Dez/25": "Dez 2025",
    "Jan/26": "Jan 2026",
    "Fev/26": "Fev 2026",
}

def load_cota_month(month_key):
    slug = COTA_MONTH_MAP[month_key]
    files = list(BASE.glob(f"Vendas Cota {slug}.csv"))
    result = {
        "total_vendas": 0, "total_plano": 0.0, "total_pago": 0.0,
        "por_origem": {}, "por_promotor": {}, "por_produto": {}, "por_status": {}
    }
    if not files:
        return result
    try:
        df = pd.read_csv(files[0], encoding='utf-8-sig', sep=';')
    except Exception:
        df = pd.read_csv(files[0], encoding='latin-1', sep=';')

    # Clean numeric cols
    for col in ['ValorTotalPlano', 'TotalPago', 'SaldoRestante', 'ValorParcela']:
        if col in df.columns:
            df[col] = df[col].apply(to_float)

    result["total_vendas"] = len(df)
    result["total_plano"] = df['ValorTotalPlano'].sum() if 'ValorTotalPlano' in df.columns else 0
    result["total_pago"] = df['TotalPago'].sum() if 'TotalPago' in df.columns else 0

    if 'OrigemVenda' in df.columns:
        for origem, grp in df.groupby('OrigemVenda'):
            result["por_origem"][str(origem)] = {
                "count": len(grp),
                "total": grp['ValorTotalPlano'].sum() if 'ValorTotalPlano' in grp.columns else 0
            }

    if 'Promotor' in df.columns:
        df_prom = df[df['Promotor'].notna() & (df['Promotor'].astype(str).str.strip() != 'NULL')]
        for prom, grp in df_prom.groupby('Promotor'):
            result["por_promotor"][str(prom).strip()] = {
                "count": len(grp),
                "total": grp['ValorTotalPlano'].sum() if 'ValorTotalPlano' in grp.columns else 0
            }

    if 'NomeProdutoAtual' in df.columns:
        for prod, grp in df.groupby('NomeProdutoAtual'):
            prod_name = str(prod).strip()
            # Simplify product name
            m = re.match(r'(Sócio \w+ Título)', prod_name)
            cat = m.group(1) if m else prod_name[:30]
            result["por_produto"][cat] = result["por_produto"].get(cat, 0) + len(grp)

    if 'StatusTitulo' in df.columns:
        for status, grp in df.groupby('StatusTitulo'):
            result["por_status"][str(status)] = len(grp)

    return result


def load_cota_all():
    return {m: load_cota_month(m) for m in MONTH_PATTERNS}


# ─── AGENTES CRM ───────────────────────────────────────────────────────────────

AGENT_FILES = {
    "Dez/25": "agent-report-31-12-2025.csv",
    "Jan/26": "agent-report-31-01-2026.csv",
    "Fev/26": "agent-report-28-02-2026.csv",
}

def parse_time_to_hours(s):
    """Converte '2 dias 3 horas' ou '1 hora 30 minutos' para horas float."""
    if not s or str(s).strip() in ('N/A', '', 'nan'):
        return None
    s = str(s).lower()
    d = re.search(r'(\d+)\s*dia', s)
    h = re.search(r'(\d+)\s*hora', s)
    m = re.search(r'(\d+)\s*minuto', s)
    total = 0
    if d:
        total += int(d.group(1)) * 24
    if h:
        total += int(h.group(1))
    if m:
        total += int(m.group(1)) / 60
    return total if total > 0 else None

def load_agent_month(month_key):
    fname = AGENT_FILES[month_key]
    fpath = BASE / fname
    result = {"total_conversas": 0, "total_resolucoes": 0, "agentes": []}
    if not fpath.exists():
        return result

    with open(fpath, encoding='utf-8-sig') as f:
        content = f.read()

    # Skip header lines until CSV data
    lines = content.split('\n')
    data_start = 0
    for i, line in enumerate(lines):
        if line.startswith('Nome do Agente') or line.startswith('Nome do Agente'):
            data_start = i
            break

    csv_content = '\n'.join(lines[data_start:])
    reader = csv.DictReader(io.StringIO(csv_content))

    for row in reader:
        nome = str(row.get('Nome do Agente', '')).strip()
        if not nome:
            continue
        convs = int(to_float(row.get('Conversas atribuídas', 0)))
        resol = int(to_float(row.get('Contagem de Resolução', 0)))
        tpr = parse_time_to_hours(row.get('Tempo médio de primeira resposta', ''))
        tres = parse_time_to_hours(row.get('Tempo médio de resolução', ''))

        result["total_conversas"] += convs
        result["total_resolucoes"] += resol
        result["agentes"].append({
            "nome": nome,
            "conversas": convs,
            "resolucoes": resol,
            "tpr_h": tpr,
            "tres_h": tres,
            "tpr_str": str(row.get('Tempo médio de primeira resposta', 'N/A')).strip(),
            "tres_str": str(row.get('Tempo médio de resolução', 'N/A')).strip(),
        })

    result["agentes"].sort(key=lambda x: x["conversas"], reverse=True)
    return result


def load_agent_all():
    return {m: load_agent_month(m) for m in MONTH_PATTERNS}


# ─── HTML GENERATION ──────────────────────────────────────────────────────────

def build_report():
    print("Carregando dados...")
    meta = load_meta_all()
    tiktok = load_tiktok_all()
    google = load_google_ads()
    dayuse = load_dayuse_all()
    cota = load_cota_all()
    agents = load_agent_all()

    months = list(MONTH_PATTERNS.keys())

    # ── Cross Metrics ──
    cross = {}
    for m in months:
        inv_total = meta[m]["investimento"] + tiktok[m]["investimento"]
        if m == "Dez/25":
            inv_total += google["investimento"]
        leads_crm = agents[m]["total_conversas"]
        cpl_real = inv_total / leads_crm if leads_crm > 0 else 0

        receita_dayuse = dayuse[m]["total_receita"]
        receita_cota = cota[m]["total_pago"]
        receita_total = receita_dayuse + receita_cota
        roas = receita_total / inv_total if inv_total > 0 else 0

        cross[m] = {
            "inv_total": inv_total,
            "leads_crm": leads_crm,
            "cpl_real": cpl_real,
            "receita_dayuse": receita_dayuse,
            "receita_cota": receita_cota,
            "receita_total": receita_total,
            "roas_estimado": roas,
        }

    # ── Chart Data ──
    labels_js = json.dumps(months)

    meta_inv = [meta[m]["investimento"] for m in months]
    tik_inv = [tiktok[m]["investimento"] for m in months]
    goo_inv = [google["investimento"] if m == "Dez/25" else 0 for m in months]
    total_inv = [meta_inv[i] + tik_inv[i] + goo_inv[i] for i in range(3)]

    meta_res = [meta[m]["resultados"] for m in months]
    tik_res = [tiktok[m]["resultados"] for m in months]
    total_leads_crm = [agents[m]["total_conversas"] for m in months]

    meta_cpl = [meta[m]["cpl_avg"] for m in months]
    tik_cpl = [tiktok[m]["cpl_avg"] for m in months]

    receita_total_list = [cross[m]["receita_total"] for m in months]
    roas_list = [round(cross[m]["roas_estimado"], 2) for m in months]

    dayuse_receita = [dayuse[m]["total_receita"] for m in months]
    cota_pago = [cota[m]["total_pago"] for m in months]

    # ── Top Promotores Fev26 ──
    prom_fev = sorted(cota["Fev/26"]["por_promotor"].items(), key=lambda x: x[1]["count"], reverse=True)[:8]

    # ── Google camps ──
    goo_camps = sorted(google["campaigns"], key=lambda x: x["investimento"], reverse=True)[:8]

    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    # ── HTML ──────────────────────────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Aquabeat | Relatório de Performance — Dez/25 a Fev/26</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  :root {{
    --bg: #f5f7fa;
    --card: #ffffff;
    --primary: #0d47a1;
    --accent: #0097a7;
    --accent2: #00bfa5;
    --danger: #d32f2f;
    --text: #212121;
    --muted: #757575;
    --border: #e0e0e0;
    --shadow: 0 2px 12px rgba(0,0,0,.08);
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: var(--text); }}

  /* ── Header ── */
  .report-header {{
    background: linear-gradient(135deg, #0d47a1 0%, #0097a7 100%);
    color: white; padding: 40px 48px 32px; position: relative; overflow: hidden;
  }}
  .report-header::after {{
    content: '💧'; font-size: 220px; position: absolute; right: -20px; top: -40px;
    opacity: .08; line-height: 1;
  }}
  .report-header h1 {{ font-size: 2.2rem; font-weight: 700; margin-bottom: 6px; }}
  .report-header p {{ font-size: 1rem; opacity: .85; }}
  .header-meta {{ margin-top: 20px; display: flex; gap: 24px; flex-wrap: wrap; }}
  .header-badge {{
    background: rgba(255,255,255,.15); border-radius: 20px;
    padding: 4px 14px; font-size: .85rem; font-weight: 500;
  }}

  /* ── Nav ── */
  .nav {{ background: var(--primary); padding: 0 48px; display: flex; gap: 0; overflow-x: auto; }}
  .nav a {{
    color: rgba(255,255,255,.75); text-decoration: none; padding: 14px 18px;
    font-size: .88rem; font-weight: 500; white-space: nowrap; border-bottom: 3px solid transparent;
    transition: all .2s;
  }}
  .nav a:hover {{ color: white; border-bottom-color: var(--accent2); }}

  /* ── Layout ── */
  .container {{ max-width: 1400px; margin: 0 auto; padding: 32px 48px; }}
  .section {{ margin-bottom: 48px; }}
  .section-title {{
    font-size: 1.35rem; font-weight: 700; color: var(--primary);
    margin-bottom: 20px; padding-bottom: 10px;
    border-bottom: 2px solid var(--accent); display: flex; align-items: center; gap: 10px;
  }}
  .section-title span {{ font-size: 1.4rem; }}

  /* ── KPI Cards ── */
  .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 16px; }}
  .kpi {{
    background: var(--card); border-radius: 12px; padding: 20px 22px;
    box-shadow: var(--shadow); border-left: 4px solid var(--accent);
    transition: transform .15s;
  }}
  .kpi:hover {{ transform: translateY(-2px); }}
  .kpi.primary {{ border-left-color: var(--primary); }}
  .kpi.success {{ border-left-color: #2e7d32; }}
  .kpi.warning {{ border-left-color: #e65100; }}
  .kpi.danger {{ border-left-color: var(--danger); }}
  .kpi-label {{ font-size: .78rem; color: var(--muted); text-transform: uppercase; font-weight: 600; margin-bottom: 8px; }}
  .kpi-value {{ font-size: 1.6rem; font-weight: 700; color: var(--text); line-height: 1; }}
  .kpi-sub {{ font-size: .78rem; color: var(--muted); margin-top: 6px; }}

  /* ── Charts ── */
  .charts-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }}
  .charts-row.triple {{ grid-template-columns: 1fr 1fr 1fr; }}
  .chart-card {{
    background: var(--card); border-radius: 12px; padding: 20px 22px;
    box-shadow: var(--shadow);
  }}
  .chart-card h3 {{ font-size: .9rem; font-weight: 600; color: var(--muted); margin-bottom: 16px; text-transform: uppercase; }}
  .chart-card canvas {{ max-height: 260px; }}

  /* ── Tables ── */
  .table-card {{
    background: var(--card); border-radius: 12px; padding: 0;
    box-shadow: var(--shadow); overflow: hidden; margin-bottom: 20px;
  }}
  .table-title {{
    padding: 16px 22px; font-size: .9rem; font-weight: 600; color: var(--primary);
    border-bottom: 1px solid var(--border); background: #f8faff;
  }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{
    padding: 10px 14px; font-size: .75rem; color: var(--muted); font-weight: 600;
    text-transform: uppercase; text-align: left; background: #f8faff;
    border-bottom: 1px solid var(--border);
  }}
  td {{ padding: 10px 14px; font-size: .85rem; border-bottom: 1px solid #f0f0f0; vertical-align: middle; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: #f8faff; }}
  .badge {{
    display: inline-block; padding: 2px 10px; border-radius: 20px;
    font-size: .72rem; font-weight: 600;
  }}
  .badge-blue {{ background: #e3f2fd; color: #1565c0; }}
  .badge-green {{ background: #e8f5e9; color: #2e7d32; }}
  .badge-orange {{ background: #fff3e0; color: #e65100; }}
  .badge-gray {{ background: #f5f5f5; color: #616161; }}

  /* ── Month tabs ── */
  .month-tabs {{ display: flex; gap: 8px; margin-bottom: 20px; flex-wrap: wrap; }}
  .month-tab {{
    padding: 8px 20px; border-radius: 20px; cursor: pointer; font-size: .85rem;
    font-weight: 600; border: 2px solid var(--border); background: var(--card);
    transition: all .2s; color: var(--muted);
  }}
  .month-tab.active {{ background: var(--primary); color: white; border-color: var(--primary); }}

  /* ── Summary row ── */
  .summary-row {{
    display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 20px;
  }}
  .platform-card {{
    background: var(--card); border-radius: 12px; padding: 20px;
    box-shadow: var(--shadow); border-top: 4px solid var(--accent);
  }}
  .platform-card.meta {{ border-top-color: #1877f2; }}
  .platform-card.tiktok {{ border-top-color: #000000; }}
  .platform-card.google {{ border-top-color: #4285f4; }}
  .platform-name {{ font-weight: 700; font-size: 1rem; margin-bottom: 12px; }}
  .platform-metric {{ display: flex; justify-content: space-between; padding: 5px 0; font-size: .85rem; border-bottom: 1px solid #f0f0f0; }}
  .platform-metric:last-child {{ border-bottom: none; }}
  .platform-metric .val {{ font-weight: 700; }}

  /* ── Alert box ── */
  .alert {{
    background: #fff3e0; border-left: 4px solid #ff6f00; border-radius: 8px;
    padding: 14px 18px; margin-bottom: 20px; font-size: .88rem;
  }}
  .alert strong {{ color: #e65100; }}

  /* ── Footer ── */
  footer {{
    text-align: center; padding: 24px; color: var(--muted); font-size: .8rem;
    border-top: 1px solid var(--border); margin-top: 40px;
  }}

  @media (max-width: 900px) {{
    .container {{ padding: 16px 20px; }}
    .report-header {{ padding: 24px 20px; }}
    .nav {{ padding: 0 20px; }}
    .charts-row, .charts-row.triple, .summary-row {{ grid-template-columns: 1fr; }}
    .kpi-grid {{ grid-template-columns: repeat(2, 1fr); }}
  }}
</style>
</head>
<body>

<!-- HEADER -->
<div class="report-header">
  <h1>Aquabeat Park — Relatório de Performance</h1>
  <p>Consolidado de Tráfego Pago, Vendas e CRM</p>
  <div class="header-meta">
    <div class="header-badge">📅 Período: Dezembro 2025 – Fevereiro 2026</div>
    <div class="header-badge">📊 Meta Ads · TikTok Ads · Google Ads · CRM · Vendas</div>
    <div class="header-badge">🕒 Gerado em {now}</div>
  </div>
</div>

<!-- NAV -->
<nav class="nav">
  <a href="#visao-geral">Visão Geral</a>
  <a href="#meta-ads">Meta Ads</a>
  <a href="#tiktok-ads">TikTok Ads</a>
  <a href="#google-ads">Google Ads</a>
  <a href="#dayuse">Vendas DayUse</a>
  <a href="#cotas">Vendas Cotas</a>
  <a href="#crm">CRM / Agentes</a>
  <a href="#cruzamento">Análise Cruzada</a>
</nav>

<div class="container">

<!-- ═══════════════════ VISÃO GERAL ═══════════════════ -->
<section class="section" id="visao-geral">
  <div class="section-title"><span>🎯</span> Visão Geral Executiva</div>

  <!-- KPI Summary -->
  <div class="kpi-grid" style="margin-bottom:20px">
    <div class="kpi primary">
      <div class="kpi-label">Investimento Total (3 meses)</div>
      <div class="kpi-value">{fmt_brl(sum(total_inv))}</div>
      <div class="kpi-sub">Meta + TikTok + Google</div>
    </div>
    <div class="kpi success">
      <div class="kpi-label">Receita Total Estimada</div>
      <div class="kpi-value">{fmt_brl(sum(receita_total_list))}</div>
      <div class="kpi-sub">DayUse + Cotas (pago)</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Total Leads/Conversas CRM</div>
      <div class="kpi-value">{fmt_n(sum(total_leads_crm))}</div>
      <div class="kpi-sub">Conversas atribuídas (3 meses)</div>
    </div>
    <div class="kpi warning">
      <div class="kpi-label">Total Ingressos DayUse</div>
      <div class="kpi-value">{fmt_n(sum(dayuse[m]['total_ingressos'] for m in months))}</div>
      <div class="kpi-sub">Vendas de ingressos avulsos</div>
    </div>
    <div class="kpi success">
      <div class="kpi-label">Total Cotas Vendidas</div>
      <div class="kpi-value">{fmt_n(sum(cota[m]['total_vendas'] for m in months))}</div>
      <div class="kpi-sub">Títulos Sócio Safira</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">ROAS Médio Estimado</div>
      <div class="kpi-value">{fmt_n(sum(roas_list)/3, 2)}x</div>
      <div class="kpi-sub">Receita / Investimento Ads</div>
    </div>
  </div>

  <!-- Investimento por plataforma por mês -->
  <div class="charts-row">
    <div class="chart-card">
      <h3>Investimento por Plataforma / Mês (R$)</h3>
      <canvas id="chartInvPlat"></canvas>
    </div>
    <div class="chart-card">
      <h3>Receita vs. Investimento por Mês (R$)</h3>
      <canvas id="chartROAS"></canvas>
    </div>
  </div>
  <div class="charts-row triple">
    <div class="chart-card">
      <h3>Leads (Resultados Ads) por Mês</h3>
      <canvas id="chartLeads"></canvas>
    </div>
    <div class="chart-card">
      <h3>Conversas CRM por Mês</h3>
      <canvas id="chartCRM"></canvas>
    </div>
    <div class="chart-card">
      <h3>Receita DayUse vs. Cotas (R$)</h3>
      <canvas id="chartReceita"></canvas>
    </div>
  </div>
</section>

<!-- ═══════════════════ META ADS ═══════════════════ -->
<section class="section" id="meta-ads">
  <div class="section-title"><span>📘</span> Meta Ads (Facebook / Instagram)</div>
  <p style="color:var(--muted);font-size:.85rem;margin-bottom:16px">
    Consolida 3 contas: <strong>CONTA_OFC</strong>, <strong>CONTA_ING</strong>, <strong>CONTA_INTERNA</strong>
  </p>

  <!-- Per-month platform cards -->
  <div class="summary-row">
"""

    for m in months:
        md = meta[m]
        html += f"""
    <div class="platform-card meta">
      <div class="platform-name">📘 Meta Ads — {m}</div>
      <div class="platform-metric"><span>Investimento</span><span class="val">{fmt_brl(md['investimento'])}</span></div>
      <div class="platform-metric"><span>Impressões</span><span class="val">{fmt_n(md['impressoes'])}</span></div>
      <div class="platform-metric"><span>Alcance</span><span class="val">{fmt_n(md['alcance'])}</span></div>
      <div class="platform-metric"><span>Resultados</span><span class="val">{fmt_n(md['resultados'])}</span></div>
      <div class="platform-metric"><span>CPL Médio</span><span class="val">{fmt_brl(md['cpl_avg'])}</span></div>
      <div class="platform-metric"><span>CPM Médio</span><span class="val">{fmt_brl(md['cpm_avg'])}</span></div>
      <div class="platform-metric"><span>CPC Médio</span><span class="val">{fmt_brl(md['cpc_avg'])}</span></div>
      <div class="platform-metric"><span>CTR Médio</span><span class="val">{fmt_pct(md['ctr_avg'])}</span></div>
    </div>
"""

    html += """
  </div>

  <div class="charts-row">
    <div class="chart-card">
      <h3>Meta — Investimento por Mês (R$)</h3>
      <canvas id="chartMetaInv"></canvas>
    </div>
    <div class="chart-card">
      <h3>Meta — CPL e CPC por Mês (R$)</h3>
      <canvas id="chartMetaCPL"></canvas>
    </div>
  </div>

  <!-- Campaigns Table - latest month (Fev/26) -->
  <div class="table-card">
    <div class="table-title">Campanhas por Conta — Fevereiro 2026</div>
    <table>
      <thead>
        <tr>
          <th>Conta</th><th>Campanha</th><th>Investimento</th>
          <th>Impressões</th><th>Alcance</th><th>Resultados</th>
          <th>CPL</th><th>CTR</th><th>CPC</th><th>CPM</th>
        </tr>
      </thead>
      <tbody>
"""

    camps_fev = sorted(meta["Fev/26"]["campaigns"], key=lambda x: x["investimento"], reverse=True)
    for c in camps_fev[:15]:
        badge_cls = {"OFC": "badge-blue", "ING": "badge-green", "INTERNA": "badge-orange"}.get(c['conta'], "badge-gray")
        html += f"""
        <tr>
          <td><span class="badge {badge_cls}">{c['conta']}</span></td>
          <td>{c['nome'][:45]}</td>
          <td>{fmt_brl(c['investimento'])}</td>
          <td>{fmt_n(c['impressoes'])}</td>
          <td>{fmt_n(c['alcance'])}</td>
          <td>{fmt_n(c['resultados'])}</td>
          <td>{fmt_brl(c['cpl']) if c['cpl'] > 0 else '—'}</td>
          <td>{fmt_pct(c['ctr'])}</td>
          <td>{fmt_brl(c['cpc']) if c['cpc'] > 0 else '—'}</td>
          <td>{fmt_brl(c['cpm']) if c['cpm'] > 0 else '—'}</td>
        </tr>
"""

    html += """
      </tbody>
    </table>
  </div>
</section>

<!-- ═══════════════════ TIKTOK ADS ═══════════════════ -->
<section class="section" id="tiktok-ads">
  <div class="section-title"><span>🎵</span> TikTok Ads</div>

  <div class="summary-row">
"""

    for m in months:
        td = tiktok[m]
        html += f"""
    <div class="platform-card tiktok">
      <div class="platform-name">🎵 TikTok Ads — {m}</div>
      <div class="platform-metric"><span>Investimento</span><span class="val">{fmt_brl(td['investimento'])}</span></div>
      <div class="platform-metric"><span>Impressões</span><span class="val">{fmt_n(td['impressoes'])}</span></div>
      <div class="platform-metric"><span>Alcance</span><span class="val">{fmt_n(td['alcance'])}</span></div>
      <div class="platform-metric"><span>Resultados</span><span class="val">{fmt_n(td['resultados'])}</span></div>
      <div class="platform-metric"><span>CPL Médio</span><span class="val">{fmt_brl(td['cpl_avg'])}</span></div>
      <div class="platform-metric"><span>CPM Médio</span><span class="val">{fmt_brl(td['cpm_avg'])}</span></div>
      <div class="platform-metric"><span>CPC Médio</span><span class="val">{fmt_brl(td['cpc_avg'])}</span></div>
    </div>
"""

    html += """
  </div>

  <div class="charts-row">
    <div class="chart-card">
      <h3>TikTok — Investimento por Mês (R$)</h3>
      <canvas id="chartTikInv"></canvas>
    </div>
    <div class="chart-card">
      <h3>TikTok — Resultados por Mês</h3>
      <canvas id="chartTikRes"></canvas>
    </div>
  </div>

  <div class="table-card">
    <div class="table-title">Campanhas TikTok — Fevereiro 2026</div>
    <table>
      <thead>
        <tr><th>Campanha</th><th>Investimento</th><th>Impressões</th><th>Alcance</th><th>Resultados</th><th>CPL</th><th>CPC</th><th>CPM</th></tr>
      </thead>
      <tbody>
"""

    for c in sorted(tiktok["Fev/26"]["campaigns"], key=lambda x: x["investimento"], reverse=True):
        html += f"""
        <tr>
          <td>{c['nome'][:50]}</td>
          <td>{fmt_brl(c['investimento'])}</td>
          <td>{fmt_n(c['impressoes'])}</td>
          <td>{fmt_n(c['alcance'])}</td>
          <td>{fmt_n(c['resultados'])}</td>
          <td>{fmt_brl(c['cpl']) if c['cpl'] > 0 else '—'}</td>
          <td>{fmt_brl(c['cpc']) if c['cpc'] > 0 else '—'}</td>
          <td>{fmt_brl(c['cpm']) if c['cpm'] > 0 else '—'}</td>
        </tr>
"""

    html += """
      </tbody>
    </table>
  </div>
</section>

<!-- ═══════════════════ GOOGLE ADS ═══════════════════ -->
<section class="section" id="google-ads">
  <div class="section-title"><span>🔍</span> Google Ads</div>
"""

    html += f"""
  <div class="alert">
    <strong>⚠️ Dados disponíveis apenas para Dezembro 2025.</strong>
    Os arquivos Google Ads (Relatorio Trafego 2026) contêm somente o período de Dezembro 2025.
    Solicite os exports de Jan/26 e Fev/26 para análise completa.
  </div>

  <div class="kpi-grid" style="margin-bottom:20px">
    <div class="kpi google">
      <div class="kpi-label">Período</div>
      <div class="kpi-value" style="font-size:1.1rem">{google['periodo']}</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Investimento</div>
      <div class="kpi-value">{fmt_brl(google['investimento'])}</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Impressões</div>
      <div class="kpi-value">{fmt_n(google['impressoes'])}</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Cliques</div>
      <div class="kpi-value">{fmt_n(google['cliques'])}</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">CTR</div>
      <div class="kpi-value">{fmt_pct(google['ctr_avg'])}</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">CPC Médio</div>
      <div class="kpi-value">{fmt_brl(google['cpc_avg'])}</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">CPM Médio</div>
      <div class="kpi-value">{fmt_brl(google['cpm_avg'])}</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Conversões</div>
      <div class="kpi-value">{fmt_n(google['conversoes'])}</div>
    </div>
    <div class="kpi warning">
      <div class="kpi-label">Custo / Conversão</div>
      <div class="kpi-value">{fmt_brl(google['custo_conv'])}</div>
    </div>
  </div>
"""

    if goo_camps:
        html += """
  <div class="table-card">
    <div class="table-title">Campanhas Google Ads — Dezembro 2025</div>
    <table>
      <thead>
        <tr><th>Campanha</th><th>Investimento</th><th>Impressões</th><th>Cliques</th><th>Conversões</th></tr>
      </thead>
      <tbody>
"""
        for c in goo_camps:
            html += f"""
        <tr>
          <td>{c['nome'][:55]}</td>
          <td>{fmt_brl(c['investimento'])}</td>
          <td>{fmt_n(c['impressoes'])}</td>
          <td>{fmt_n(c['cliques'])}</td>
          <td>{fmt_n(c['conversoes'])}</td>
        </tr>
"""
        html += "      </tbody>\n    </table>\n  </div>\n"

    html += "</section>\n"

    # ═══ DAYUSE ═══
    html += """
<section class="section" id="dayuse">
  <div class="section-title"><span>🎟️</span> Vendas DayUse</div>

  <div class="summary-row">
"""
    for m in months:
        dd = dayuse[m]
        html += f"""
    <div class="platform-card" style="border-top-color:#00897b">
      <div class="platform-name">🎟️ DayUse — {m}</div>
      <div class="platform-metric"><span>Total Ingressos</span><span class="val">{fmt_n(dd['total_ingressos'])}</span></div>
      <div class="platform-metric"><span>Receita Total</span><span class="val">{fmt_brl(dd['total_receita'])}</span></div>
      <div class="platform-metric"><span>Ticket Médio</span><span class="val">{fmt_brl(dd['ticket_medio'])}</span></div>
    </div>
"""

    html += """
  </div>

  <div class="charts-row">
    <div class="chart-card">
      <h3>Receita DayUse por Mês (R$)</h3>
      <canvas id="chartDayInv"></canvas>
    </div>
    <div class="chart-card">
      <h3>Ingressos Vendidos por Mês</h3>
      <canvas id="chartDayIng"></canvas>
    </div>
  </div>

  <!-- Top consultores Fev/26 -->
  <div class="table-card">
    <div class="table-title">Top Consultores DayUse — Fevereiro 2026</div>
    <table>
      <thead><tr><th>#</th><th>Consultor</th><th>Total Ingressos</th><th>Receita Total</th><th>Ticket Médio</th></tr></thead>
      <tbody>
"""
    for i, c in enumerate(dayuse["Fev/26"]["consultores"], 1):
        html += f"""
        <tr>
          <td><strong>#{i}</strong></td>
          <td>{c['nome'][:40]}</td>
          <td>{fmt_n(c['ingressos'])}</td>
          <td>{fmt_brl(c['receita'])}</td>
          <td>{fmt_brl(c['ticket'])}</td>
        </tr>
"""
    html += "      </tbody>\n    </table>\n  </div>\n</section>\n"

    # ═══ COTAS ═══
    html += """
<section class="section" id="cotas">
  <div class="section-title"><span>🏆</span> Vendas Cotas / Títulos Sócio</div>

  <div class="summary-row">
"""
    for m in months:
        cd = cota[m]
        html += f"""
    <div class="platform-card" style="border-top-color:#7b1fa2">
      <div class="platform-name">🏆 Cotas — {m}</div>
      <div class="platform-metric"><span>Títulos Vendidos</span><span class="val">{fmt_n(cd['total_vendas'])}</span></div>
      <div class="platform-metric"><span>Valor Total dos Planos</span><span class="val">{fmt_brl(cd['total_plano'])}</span></div>
      <div class="platform-metric"><span>Total Pago (recebido)</span><span class="val">{fmt_brl(cd['total_pago'])}</span></div>
    </div>
"""

    html += """
  </div>

  <div class="charts-row">
    <div class="chart-card">
      <h3>Cotas — Valor dos Planos por Mês (R$)</h3>
      <canvas id="chartCotaPlano"></canvas>
    </div>
    <div class="chart-card">
      <h3>Cotas — Títulos Vendidos por Mês</h3>
      <canvas id="chartCotaVendas"></canvas>
    </div>
  </div>
"""

    # Origem vendas Fev/26
    if cota["Fev/26"]["por_origem"]:
        html += """
  <div class="charts-row">
    <div class="chart-card">
      <h3>Origem das Vendas — Fevereiro 2026</h3>
      <canvas id="chartCotaOrigem"></canvas>
    </div>
    <div class="chart-card">
      <h3>Produtos Mais Vendidos — Fevereiro 2026</h3>
      <canvas id="chartCotaProd"></canvas>
    </div>
  </div>
"""

    # Top promotores table
    html += """
  <div class="table-card">
    <div class="table-title">Top Promotores — Fevereiro 2026</div>
    <table>
      <thead><tr><th>#</th><th>Promotor</th><th>Títulos Vendidos</th><th>Valor Total Planos</th></tr></thead>
      <tbody>
"""
    for i, (prom, data) in enumerate(prom_fev, 1):
        html += f"""
        <tr>
          <td><strong>#{i}</strong></td>
          <td>{prom[:40]}</td>
          <td>{fmt_n(data['count'])}</td>
          <td>{fmt_brl(data['total'])}</td>
        </tr>
"""
    html += "      </tbody>\n    </table>\n  </div>\n</section>\n"

    # ═══ CRM / AGENTES ═══
    html += """
<section class="section" id="crm">
  <div class="section-title"><span>💬</span> CRM — Agentes (Profluxus / Chatwoot)</div>

  <div class="summary-row">
"""
    for m in months:
        ag = agents[m]
        html += f"""
    <div class="platform-card" style="border-top-color:#f57c00">
      <div class="platform-name">💬 CRM — {m}</div>
      <div class="platform-metric"><span>Conversas Atribuídas</span><span class="val">{fmt_n(ag['total_conversas'])}</span></div>
      <div class="platform-metric"><span>Resoluções</span><span class="val">{fmt_n(ag['total_resolucoes'])}</span></div>
      <div class="platform-metric"><span>Agentes Ativos</span><span class="val">{len(ag['agentes'])}</span></div>
    </div>
"""

    html += """
  </div>

  <div class="charts-row">
    <div class="chart-card">
      <h3>Conversas Atribuídas por Mês</h3>
      <canvas id="chartAgConv"></canvas>
    </div>
    <div class="chart-card">
      <h3>Resoluções por Mês</h3>
      <canvas id="chartAgRes"></canvas>
    </div>
  </div>
"""

    for m in months:
        ag = agents[m]
        if not ag["agentes"]:
            continue
        html += f"""
  <div class="table-card">
    <div class="table-title">Agentes — {m}</div>
    <table>
      <thead>
        <tr>
          <th>#</th><th>Agente</th><th>Conversas</th><th>Resoluções</th>
          <th>Tempo 1ª Resposta</th><th>Tempo Resolução</th>
        </tr>
      </thead>
      <tbody>
"""
        for i, a in enumerate(ag["agentes"], 1):
            html += f"""
        <tr>
          <td><strong>#{i}</strong></td>
          <td>{a['nome'][:40]}</td>
          <td>{fmt_n(a['conversas'])}</td>
          <td>{fmt_n(a['resolucoes'])}</td>
          <td>{a['tpr_str']}</td>
          <td>{a['tres_str']}</td>
        </tr>
"""
        html += "      </tbody>\n    </table>\n  </div>\n"

    html += "</section>\n"

    # ═══ ANÁLISE CRUZADA ═══
    html += """
<section class="section" id="cruzamento">
  <div class="section-title"><span>🔗</span> Análise Cruzada — Ads + CRM + Vendas</div>

  <div class="alert">
    <strong>ℹ️ Nota sobre atribuição:</strong> O CPL Real e o ROAS Estimado abaixo cruzam o gasto em Ads
    com o volume de conversas do CRM e a receita total (DayUse + Cotas pagas). A atribuição exata exige
    UTMs configuradas nas landing pages e captura no CRM. Esses valores são estimativas do período.
  </div>

  <div class="table-card">
    <div class="table-title">Resumo Cruzado por Mês</div>
    <table>
      <thead>
        <tr>
          <th>Mês</th>
          <th>Invest. Total Ads</th>
          <th>Conversas CRM</th>
          <th>CPL Real (Ads÷CRM)</th>
          <th>Receita DayUse</th>
          <th>Receita Cotas</th>
          <th>Receita Total</th>
          <th>ROAS Estimado</th>
        </tr>
      </thead>
      <tbody>
"""
    for m in months:
        cx = cross[m]
        roas_val = cx['roas_estimado']
        roas_cls = "badge-green" if roas_val >= 3 else ("badge-orange" if roas_val >= 1 else "badge-danger")
        html += f"""
        <tr>
          <td><strong>{m}</strong></td>
          <td>{fmt_brl(cx['inv_total'])}</td>
          <td>{fmt_n(cx['leads_crm'])}</td>
          <td>{fmt_brl(cx['cpl_real'])}</td>
          <td>{fmt_brl(cx['receita_dayuse'])}</td>
          <td>{fmt_brl(cx['receita_cota'])}</td>
          <td><strong>{fmt_brl(cx['receita_total'])}</strong></td>
          <td><span class="badge {roas_cls}">{fmt_n(roas_val, 2)}x</span></td>
        </tr>
"""

    html += """
      </tbody>
    </table>
  </div>

  <div class="charts-row">
    <div class="chart-card">
      <h3>CPL Real por Mês (R$)</h3>
      <canvas id="chartCPLReal"></canvas>
    </div>
    <div class="chart-card">
      <h3>ROAS Estimado por Mês</h3>
      <canvas id="chartROASMes"></canvas>
    </div>
  </div>

  <div class="alert" style="background:#e8f5e9;border-left-color:#2e7d32;margin-top:20px">
    <strong>✅ O que falta para análise completa:</strong><br><br>
    1. <strong>Atribuição de campanha ao lead no CRM</strong> — configurar UTMs nas landing pages e capturar no CRM<br>
    2. <strong>Registro de valor (R$) das vendas no CRM</strong> — campo financeiro ou integração com sistema de vendas<br>
    3. <strong>Taxa de conversão da landing page</strong> — Google Analytics / Meta Pixel com evento de lead<br>
    4. <strong>Google Ads Jan/26 e Fev/26</strong> — exportar relatórios dos meses faltantes
  </div>
</section>

</div><!-- /container -->

<footer>
  Relatório gerado automaticamente por <strong>Aquabeat Ads Report Generator</strong> · {now}<br>
  Dados: Meta Ads (OFC/ING/INTERNA) · TikTok Ads · Google Ads · Profluxus CRM · Sistema de Vendas
</footer>
"""

    # ═══ JAVASCRIPT ═══
    def js_arr(lst):
        return json.dumps([round(float(v), 2) for v in lst])

    # Colors
    C_BLUE = "#1877f2"
    C_TIKTOK = "#444444"
    C_GOOGLE = "#4285f4"
    C_GREEN = "#00897b"
    C_PURPLE = "#7b1fa2"
    C_ORANGE = "#f57c00"
    C_CYAN = "#0097a7"
    C_RED = "#d32f2f"
    C_AMBER = "#ffa000"

    # Origem data for Fev/26
    origens_fev = cota["Fev/26"]["por_origem"]
    orig_labels = json.dumps(list(origens_fev.keys()))
    orig_counts = json.dumps([v["count"] for v in origens_fev.values()])

    prods_fev = cota["Fev/26"]["por_produto"]
    prod_labels = json.dumps(list(prods_fev.keys())[:8])
    prod_counts = json.dumps(list(prods_fev.values())[:8])

    cpl_real_list = [cross[m]["cpl_real"] for m in months]
    roas_m_list = [cross[m]["roas_estimado"] for m in months]

    cota_plano = [cota[m]["total_plano"] for m in months]
    cota_vendas_cnt = [cota[m]["total_vendas"] for m in months]

    dayuse_ing = [dayuse[m]["total_ingressos"] for m in months]

    ag_convs = [agents[m]["total_conversas"] for m in months]
    ag_ress = [agents[m]["total_resolucoes"] for m in months]

    html += f"""
<script>
const LABELS = {labels_js};
const MONTHS = {labels_js};

function mkChart(id, type, datasets, opts) {{
  const ctx = document.getElementById(id);
  if (!ctx) return;
  return new Chart(ctx, {{
    type: type,
    data: {{ labels: LABELS, datasets: datasets }},
    options: {{
      responsive: true, maintainAspectRatio: true,
      plugins: {{ legend: {{ position: 'bottom', labels: {{ boxWidth: 12, font: {{ size: 11 }} }} }} }},
      scales: type === 'bar' || type === 'line' ? {{
        x: {{ grid: {{ display: false }} }},
        y: {{ grid: {{ color: '#f0f0f0' }}, beginAtZero: true }}
      }} : undefined,
      ...opts
    }}
  }});
}}

// ─── Visão Geral ───────────────────────────────
mkChart('chartInvPlat', 'bar', [
  {{ label: 'Meta Ads', data: {js_arr(meta_inv)}, backgroundColor: '{C_BLUE}' }},
  {{ label: 'TikTok Ads', data: {js_arr(tik_inv)}, backgroundColor: '{C_TIKTOK}' }},
  {{ label: 'Google Ads', data: {js_arr(goo_inv)}, backgroundColor: '{C_GOOGLE}' }},
], {{ plugins: {{ tooltip: {{ callbacks: {{ label: c => 'R$ ' + c.raw.toLocaleString('pt-BR', {{minimumFractionDigits:2}}) }} }} }} }});

mkChart('chartROAS', 'bar', [
  {{ label: 'Investimento Ads', data: {js_arr(total_inv)}, backgroundColor: '{C_CYAN}', yAxisID: 'y' }},
  {{ label: 'Receita Total', data: {js_arr(receita_total_list)}, backgroundColor: '{C_GREEN}', yAxisID: 'y' }},
]);

mkChart('chartLeads', 'bar', [
  {{ label: 'Leads Meta', data: {js_arr(meta_res)}, backgroundColor: '{C_BLUE}' }},
  {{ label: 'Leads TikTok', data: {js_arr(tik_res)}, backgroundColor: '{C_TIKTOK}' }},
]);

mkChart('chartCRM', 'bar', [
  {{ label: 'Conversas CRM', data: {js_arr(total_leads_crm)}, backgroundColor: '{C_ORANGE}' }},
]);

mkChart('chartReceita', 'bar', [
  {{ label: 'DayUse', data: {js_arr(dayuse_receita)}, backgroundColor: '{C_GREEN}' }},
  {{ label: 'Cotas (pago)', data: {js_arr(cota_pago)}, backgroundColor: '{C_PURPLE}' }},
]);

// ─── Meta Ads ───────────────────────────────────
mkChart('chartMetaInv', 'bar', [
  {{ label: 'Investimento Meta (R$)', data: {js_arr(meta_inv)}, backgroundColor: '{C_BLUE}' }},
]);
mkChart('chartMetaCPL', 'line', [
  {{ label: 'CPL Meta (R$)', data: {js_arr(meta_cpl)}, borderColor: '{C_BLUE}', tension:.3, fill:false }},
  {{ label: 'CPL TikTok (R$)', data: {js_arr(tik_cpl)}, borderColor: '{C_TIKTOK}', tension:.3, fill:false }},
]);

// ─── TikTok ─────────────────────────────────────
mkChart('chartTikInv', 'bar', [
  {{ label: 'Investimento TikTok (R$)', data: {js_arr(tik_inv)}, backgroundColor: '{C_TIKTOK}' }},
]);
mkChart('chartTikRes', 'bar', [
  {{ label: 'Resultados TikTok', data: {js_arr(tik_res)}, backgroundColor: '#757575' }},
]);

// ─── DayUse ─────────────────────────────────────
mkChart('chartDayInv', 'bar', [
  {{ label: 'Receita DayUse (R$)', data: {js_arr(dayuse_receita)}, backgroundColor: '{C_GREEN}' }},
]);
mkChart('chartDayIng', 'bar', [
  {{ label: 'Ingressos Vendidos', data: {js_arr(dayuse_ing)}, backgroundColor: '#26a69a' }},
]);

// ─── Cotas ──────────────────────────────────────
mkChart('chartCotaPlano', 'bar', [
  {{ label: 'Valor Total Planos (R$)', data: {js_arr(cota_plano)}, backgroundColor: '{C_PURPLE}' }},
  {{ label: 'Total Pago (R$)', data: {js_arr(cota_pago)}, backgroundColor: '#ba68c8' }},
]);
mkChart('chartCotaVendas', 'bar', [
  {{ label: 'Títulos Vendidos', data: {js_arr(cota_vendas_cnt)}, backgroundColor: '#ab47bc' }},
]);

mkChart('chartCotaOrigem', 'doughnut', [
  {{ data: {orig_counts}, backgroundColor: ['#1877f2','#00897b','#f57c00','#7b1fa2','#d32f2f','#0097a7'] }}
], {{
  plugins: {{
    legend: {{ position: 'right' }},
    tooltip: {{ callbacks: {{ label: c => c.label + ': ' + c.raw }} }}
  }},
  labels: {orig_labels}
}});

// Override chart origem labels
const cotaOrigemChart = Chart.getChart('chartCotaOrigem');

mkChart('chartCotaProd', 'doughnut', [
  {{ data: {prod_counts}, backgroundColor: ['#1877f2','#00897b','#f57c00','#7b1fa2','#d32f2f','#0097a7','#ffa000','#78909c'] }}
], {{
  plugins: {{
    legend: {{ position: 'right' }},
    tooltip: {{ callbacks: {{ label: c => c.raw + ' títulos' }} }}
  }},
  labels: {prod_labels}
}});

// ─── Agentes ────────────────────────────────────
mkChart('chartAgConv', 'bar', [
  {{ label: 'Conversas Atribuídas', data: {js_arr(ag_convs)}, backgroundColor: '{C_ORANGE}' }},
]);
mkChart('chartAgRes', 'bar', [
  {{ label: 'Resoluções', data: {js_arr(ag_ress)}, backgroundColor: '#ef6c00' }},
]);

// ─── Cruzamento ──────────────────────────────────
mkChart('chartCPLReal', 'line', [
  {{ label: 'CPL Real (R$)', data: {js_arr(cpl_real_list)}, borderColor: '{C_RED}', backgroundColor:'rgba(211,47,47,.1)', tension:.3, fill:true }},
]);
mkChart('chartROASMes', 'bar', [
  {{ label: 'ROAS Estimado (x)', data: {js_arr(roas_m_list)}, backgroundColor: ctx => {{
    const v = ctx.dataset.data[ctx.dataIndex];
    return v >= 3 ? '#2e7d32' : v >= 1 ? '#ffa000' : '#d32f2f';
  }} }},
]);

// Fix doughnut labels
document.querySelectorAll('canvas').forEach(c => {{
  const chart = Chart.getChart(c);
  if (chart && chart.config.type === 'doughnut' && chart.config.options?.labels) {{
    chart.data.labels = chart.config.options.labels;
    chart.update();
  }}
}});
</script>
</body>
</html>"""

    return html


if __name__ == "__main__":
    print("🚀 Gerando relatório Aquabeat...")
    html = build_report()
    output = BASE / "relatorio_aquabeat_performance.html"
    output.write_text(html, encoding="utf-8")
    size_kb = output.stat().st_size // 1024
    print(f"✅ Relatório salvo em: {output}")
    print(f"   Tamanho: {size_kb} KB")
    print(f"   Abra no navegador para visualizar.")
