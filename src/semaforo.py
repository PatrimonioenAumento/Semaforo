"""
Semáforo de Mercado Global — versión GitHub Actions compatible
23 indicadores · 6 capas · horizonte 1-3 meses
Fuentes: Yahoo Finance · FRED API JSON · cálculo propio
"""

import yfinance as yf
import pandas as pd
import numpy as np
import requests
import json
import os
import warnings
from datetime import datetime, timedelta

warnings.filterwarnings('ignore')

FECHA = datetime.now().strftime("%d %b %Y %H:%M")
FRED_API = "https://api.stlouisfed.org/fred/series/observations"
FRED_KEY = "b3a67acffe696bc5e7fcc4af78ce9bc3"  # clave pública demo de FRED

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def download_yf(ticker, period='2y'):
    try:
        df = yf.download(ticker, period=period, interval='1d',
                         progress=False, auto_adjust=True)
        if df.empty:
            return pd.Series(dtype=float)
        s = df['Close'].dropna()
        if isinstance(s, pd.DataFrame):
            s = s.iloc[:, 0]
        return s
    except Exception as e:
        print(f"  ✗ YF {ticker}: {e}")
        return pd.Series(dtype=float)

def download_fred(series_id, max_retries=3):
    """FRED via CSV endpoint, con reintentos y timeout ampliado"""
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv"
    params = {'id': series_id}
    headers = {'User-Agent': 'Mozilla/5.0 (compatible; SemaforoBot/1.0)'}

    for attempt in range(1, max_retries + 1):
        try:
            r = requests.get(url, params=params, timeout=45, headers=headers)
            r.raise_for_status()
            lines = r.text.strip().split('\n')
            rows = []
            for line in lines[1:]:
                parts = line.split(',')
                if len(parts) >= 2:
                    try:
                        d = pd.to_datetime(parts[0].strip().strip('"'))
                        v = float(parts[1].strip().strip('"'))
                        rows.append({'date': d, 'value': v})
                    except:
                        pass
            if not rows:
                raise ValueError("Sin filas válidas")
            df = pd.DataFrame(rows).set_index('date').sort_index()
            return df
        except Exception as e:
            if attempt < max_retries:
                print(f"  ⟳ FRED {series_id}: intento {attempt} falló ({e}), reintentando...")
                continue
            print(f"  ✗ FRED {series_id}: {e}")
            return pd.DataFrame()
    return pd.DataFrame()

def pct_n(s, n):
    if s is None or len(s) < n + 1:
        return None
    try:
        return (float(s.iloc[-1]) / float(s.iloc[-(n + 1)]) - 1) * 100
    except:
        return None

def sma(s, n):
    if s is None or len(s) < n:
        return None
    return float(s.iloc[-n:].mean())

def mom13612u(s):
    if s is None or len(s) < 253:
        return None
    vals = [pct_n(s, d) for d in [21, 63, 126, 252]]
    if any(v is None for v in vals):
        return None
    return sum(vals) / 4

def fetch_greed_fear():
    """Alternative Fear & Greed via alternative.me — funciona desde servidores"""
    try:
        r = requests.get('https://api.alternative.me/fng/?limit=1',
                        timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        r.raise_for_status()
        d = r.json()
        score = int(d['data'][0]['value'])
        label = d['data'][0]['value_classification']
        return score, label
    except Exception as e:
        print(f"  ✗ Fear&Greed: {e}")
        return None, None

# ─────────────────────────────────────────────
# DESCARGA DE DATOS YAHOO FINANCE
# ─────────────────────────────────────────────

print("Descargando Yahoo Finance...")
TICKERS = {
    'SPX':  '^GSPC', 'QQQ':  'QQQ',  'XLU':  'XLU',
    'RSP':  'RSP',   'XLY':  'XLY',  'XLP':  'XLP',
    'VWO':  'VWO',   'BND':  'BND',  'TIP':  'TIP',
    'CPER': 'CPER',  'GLD':  'GLD',  'UUP':  'UUP',
    'VIX':  '^VIX',
    # Amplitud via ETFs proxy (no dependen de tickers NYSE especiales)
    'IWM':  'IWM',   # Russell 2000 — proxy amplitud small caps
    'MDY':  'MDY',   # S&P MidCap 400 — proxy amplitud mid caps
    'XLF':  'XLF',   # Financials — proxy salud interna mercado
    'XLK':  'XLK',   # Tech
    'XLV':  'XLV',   # Healthcare defensivo
    'XLC':  'XLC',   # Communications
}

D = {}
for k, t in TICKERS.items():
    D[k] = download_yf(t)
    status = f"{len(D[k])} sesiones" if len(D[k]) > 0 else "sin datos"
    print(f"  {'✓' if len(D[k]) > 0 else '✗'} {t}: {status}")

# ─────────────────────────────────────────────
# DESCARGA FRED
# ─────────────────────────────────────────────

print("\nDescargando FRED...")
F = {}
for name, sid in [('HY','BAMLH0A0HYM2'), ('CURVE','T10Y2Y'), ('PMI','NAPM'), ('EFFR','EFFR'), ('UPPER','DFEDTARU')]:
    F[name] = download_fred(sid)
    status = f"{len(F[name])} obs, último: {F[name].index[-1].strftime('%d %b %Y') if len(F[name])>0 else 'n/a'}"
    print(f"  {'✓' if len(F[name])>0 else '✗'} {sid}: {status}")


print("\nDescargando Fear & Greed...")
fg_score, fg_label = fetch_greed_fear()
if fg_score:
    print(f"  ✓ Fear&Greed (alternative.me): {fg_score} ({fg_label})")

# ─────────────────────────────────────────────
# CÁLCULO DE INDICADORES
# ─────────────────────────────────────────────

results = {}

def add(id_, name, sig, val, w, src, layer):
    results[id_] = {'name': name, 'sig': sig, 'val': val, 'w': w, 'src': src, 'layer': layer}

print("\nCalculando indicadores...")
spx = D['SPX']

# 1. SMA 200
if len(spx) >= 200:
    l, s200 = float(spx.iloc[-1]), sma(spx, 200)
    p = (l / s200 - 1) * 100
    add('sma200', 'SMA 200 S&P 500',
        'g' if p >= 2 else ('y' if p >= -2 else 'r'),
        f"SPX {l:.0f} vs SMA200 {s200:.0f} ({p:+.1f}%)", 3, 'YF', 'tendencia')

# 2. Momentum 13612U
m = mom13612u(spx)
if m is not None:
    add('mom13612', 'Momentum 13612U SPY',
        'g' if m > 2 else ('y' if m > -1 else 'r'),
        f"13612U: {m:+.2f}% (media 1/3/6/12m)", 2, 'YF', 'tendencia')

# 3. QQQ/XLU
r1q, r1x = pct_n(D['QQQ'], 21), pct_n(D['XLU'], 21)
if r1q and r1x:
    d = r1q - r1x
    add('qqqxlu', 'QQQ/XLU (tipos implícitos)',
        'g' if d > 3 else ('y' if d > -3 else 'r'),
        f"QQQ vs XLU 1m: {d:+.1f}%", 2, 'YF', 'tendencia')

# 4. A/D line proxy: % ETFs sectoriales sobre SMA50
# Usamos 8 ETFs sectoriales como proxy de amplitud
sector_etfs = ['QQQ','XLU','XLY','XLP','XLF','XLK','XLV','XLC','IWM','MDY']
above_sma50 = 0
total_etfs = 0
for etf in sector_etfs:
    s = D.get(etf, pd.Series())
    if len(s) >= 50:
        s50 = sma(s, 50)
        if s50:
            total_etfs += 1
            if float(s.iloc[-1]) > s50:
                above_sma50 += 1
if total_etfs > 0:
    pct_above = above_sma50 / total_etfs * 100
    add('adline', 'Amplitud sectorial (% ETFs > SMA50)',
        'g' if pct_above > 65 else ('y' if pct_above > 45 else 'r'),
        f"{above_sma50}/{total_etfs} ETFs sobre SMA50 ({pct_above:.0f}%)", 2, 'YF', 'amplitud')

# 5. RSP/SPY — concentración
r3r, r3s = pct_n(D['RSP'], 63), pct_n(spx, 63)
if r3r and r3s:
    d = r3r - r3s
    add('rspspy', 'RSP/SPY (concentración mega-caps)',
        'g' if d > 1 else ('y' if d > -3 else 'r'),
        f"RSP vs SPY 3m: {d:+.1f}% ({'amplitud buena' if d > 1 else 'concentrado'})", 1, 'YF', 'amplitud')

# 6. Small caps vs Large caps (IWM/SPY) proxy NYHL
r3i, r3s2 = pct_n(D['IWM'], 63), pct_n(spx, 63)
if r3i and r3s2:
    d = r3i - r3s2
    add('nyhl', 'IWM/SPY (small vs large caps)',
        'g' if d > 2 else ('y' if d > -3 else 'r'),
        f"IWM vs SPY 3m: {d:+.1f}% ({'small caps lideran' if d > 2 else 'large caps lideran' if d < -3 else 'neutro'})",
        2, 'YF', 'amplitud')

# 7. Breadth Thrust proxy — aceleración de amplitud sectorial
# Comparar % ETFs sobre SMA50 ahora vs hace 10 días
above_10d = 0
total_10d = 0
for etf in sector_etfs:
    s = D.get(etf, pd.Series())
    if len(s) >= 60:
        s50_10d = float(s.iloc[-60:-10].mean()) if len(s) >= 60 else None
        price_10d = float(s.iloc[-11]) if len(s) >= 11 else None
        if s50_10d and price_10d:
            total_10d += 1
            if price_10d > s50_10d:
                above_10d += 1
if total_10d > 0 and total_etfs > 0:
    prev_pct = above_10d / total_10d * 100
    curr_pct = above_sma50 / total_etfs * 100
    bt_signal = prev_pct < 40 and curr_pct > 61
    add('breadth', 'Breadth Thrust proxy',
        'g' if bt_signal else 'n',
        f'Señal activa: {prev_pct:.0f}%→{curr_pct:.0f}%' if bt_signal else f'Sin señal ({curr_pct:.0f}% ETFs alcistas)',
        2, 'calc', 'amplitud')

# 8. Carlucci proxy — % ETFs sobre SMA200
above_sma200 = sum(1 for etf in sector_etfs
                   if len(D.get(etf, [])) >= 200 and float(D[etf].iloc[-1]) > sma(D[etf], 200))
total_200 = sum(1 for etf in sector_etfs if len(D.get(etf, [])) >= 200)
if total_200 > 0:
    pct200 = above_sma200 / total_200 * 100
    add('carlucci', 'Carlucci proxy (% ETFs > SMA200)',
        'g' if pct200 >= 65 else ('y' if pct200 >= 45 else 'r'),
        f"{above_sma200}/{total_200} ETFs sobre SMA200 ({pct200:.0f}%, umbral 65%)", 2, 'YF', 'amplitud')

# 9. Fosback proxy — dispersión sectorial
retornos_1m = [pct_n(D.get(e), 21) for e in sector_etfs if pct_n(D.get(e), 21) is not None]
if len(retornos_1m) >= 5:
    dispersion = np.std(retornos_1m)
    add('fosback', 'Fosback proxy (dispersión sectorial)',
        'g' if dispersion < 3 else ('y' if dispersion < 6 else 'r'),
        f"Dispersión retornos 1m: {dispersion:.1f}% ({'coherente' if dispersion < 3 else 'moderada' if dispersion < 6 else 'incoherente'})",
        1, 'calc', 'amplitud')

# 10. XLY/XLP
r1y, r1p = pct_n(D['XLY'], 21), pct_n(D['XLP'], 21)
if r1y and r1p:
    d = r1y - r1p
    add('xlyxlp', 'XLY/XLP (ciclo vs defensivo)',
        'g' if d > 2 else ('y' if d > -2 else 'r'),
        f"XLY vs XLP 1m: {d:+.1f}%", 2, 'YF', 'flujos')

# 11. VWO
r1v, r3v = pct_n(D['VWO'], 21), pct_n(D['VWO'], 63)
if r1v is not None:
    add('vwo', 'VWO canario emergentes',
        'g' if (r1v > 0 and (r3v or 0) > 0) else ('r' if r1v < -3 else 'y'),
        f"VWO 1m: {r1v:+.1f}%{f' | 3m: {r3v:+.1f}%' if r3v else ''}", 2, 'YF', 'flujos')

# 12. BND
r1b = pct_n(D['BND'], 21)
if r1b is not None:
    add('bnd', 'BND canario renta fija',
        'g' if r1b > 0 else ('y' if r1b > -1 else 'r'),
        f"BND 1m: {r1b:+.1f}%", 2, 'YF', 'flujos')

# 13. Copper/Gold
r1c, r1g = pct_n(D['CPER'], 21), pct_n(D['GLD'], 21)
if r1c and r1g:
    d = r1c - r1g
    add('coppergold', 'Copper/Gold ratio',
        'g' if d > 2 else ('y' if d > -2 else 'r'),
        f"CPER vs GLD 1m: {d:+.1f}%", 2, 'YF', 'flujos')

# 14. TIP Keller
m_tip = mom13612u(D['TIP'])
if m_tip is not None:
    add('tip', 'TIP momentum (Keller)',
        'g' if m_tip > 0.5 else ('y' if m_tip > -0.5 else 'r'),
        f"TIP 13612U: {m_tip:+.2f}% (Keller HAA)", 2, 'YF', 'flujos')

# 15. PMI (FRED)
pmi_df = F.get('PMI', pd.DataFrame())
if len(pmi_df) > 0:
    pmi_v = float(pmi_df['value'].iloc[-1])
    pmi_d = pmi_df.index[-1].strftime('%b %Y')
    add('pmi', 'ISM PMI manufacturero USA',
        'g' if pmi_v > 52 else ('y' if pmi_v > 50 else 'r'),
        f"ISM PMI: {pmi_v:.1f} ({pmi_d})", 2, 'FRED', 'macro')

# 16. Curva 2Y-10Y (FRED)
curve_df = F.get('CURVE', pd.DataFrame())
if len(curve_df) > 0:
    yc_v = float(curve_df['value'].iloc[-1])
    yc_d = curve_df.index[-1].strftime('%d %b')
    add('yieldcurve', 'Curva 2Y-10Y USA',
        'g' if yc_v > 0.25 else ('y' if yc_v > -0.25 else 'r'),
        f"2Y-10Y: {yc_v:+.2f}% ({yc_v*100:+.0f}pb) · {yc_d}", 2, 'FRED', 'macro')

# 17. EPS proxy
if len(spx) >= 200:
    r1s, r6s = pct_n(spx, 21), pct_n(spx, 126)
    if r1s and r6s:
        monthly_avg = r6s / 6
        acel = r1s - monthly_avg
        add('eps', 'EPS proxy (momentum SPY)',
            'g' if acel > 1.5 else ('y' if acel > -1.5 else 'r'),
            f"Aceleración SPY: {acel:+.1f}% vs media 6m ({'beneficios sorprendiendo' if acel > 1.5 else 'en línea' if acel > -1.5 else 'presión'})",
            2, 'calc', 'macro')

# 18. VIX
if len(D['VIX']) > 0:
    v = float(D['VIX'].iloc[-1])
    add('vix', 'VIX (fear gauge)',
        'g' if v < 18 else ('y' if v < 28 else 'r'),
        f"VIX: {v:.2f}", 2, 'YF', 'sentimiento')

# 19. Put/Call proxy — ratio VIX vs VIX3M
vix3m = download_yf('^VIX3M')
if len(D['VIX']) > 0 and len(vix3m) > 0:
    vix_now = float(D['VIX'].iloc[-1])
    vix3m_now = float(vix3m.iloc[-1])
    ratio_vix = vix_now / vix3m_now if vix3m_now > 0 else 1
    add('putcall', 'VIX/VIX3M ratio (curva volatilidad)',
        'g' if ratio_vix < 0.9 else ('y' if ratio_vix < 1.05 else 'r'),
        f"VIX {vix_now:.1f} / VIX3M {vix3m_now:.1f} = {ratio_vix:.2f} ({'contango' if ratio_vix < 0.9 else 'backwardation' if ratio_vix > 1.05 else 'normal'})",
        1, 'YF', 'sentimiento')
else:
    if len(D['VIX']) > 0:
        v = float(D['VIX'].iloc[-1])
        add('putcall', 'VIX nivel',
            'g' if v < 16 else ('y' if v < 22 else 'r'),
            f"VIX: {v:.2f} (proxy put/call)", 1, 'YF', 'sentimiento')

# 20. Fear & Greed (alternative.me)
if fg_score is not None:
    add('aaii', 'Fear & Greed Index (alternative.me)',
        'g' if fg_score < 35 else ('r' if fg_score > 70 else 'y'),
        f"Score: {fg_score}/100 · {fg_label} ({'contrarian alcista' if fg_score < 35 else 'precaución' if fg_score > 70 else 'neutro'})",
        1, 'web', 'sentimiento')
else:
    add('aaii', 'Fear & Greed Index',
        'y', 'Dato no disponible', 1, 'web', 'sentimiento')

# 21. Fed sesgo (FRED EFFR)
effr_df  = F.get('EFFR', pd.DataFrame())
upper_df = F.get('UPPER', pd.DataFrame())
if len(effr_df) > 0 and len(upper_df) > 0:
    current = float(effr_df['value'].iloc[-1])
    upper   = float(upper_df['value'].iloc[-1])
    upper_3m = float(upper_df['value'].iloc[-60]) if len(upper_df) >= 60 else upper
    if upper > upper_3m:
        fed_sig = 'r'
        fed_txt = f"Fed Funds: {current:.2f}% · subiendo vs hace 3m → restrictivo"
    elif upper < upper_3m:
        fed_sig = 'g'
        fed_txt = f"Fed Funds: {current:.2f}% · bajando vs hace 3m → expansivo"
    else:
        fed_sig = 'y'
        fed_txt = f"Fed Funds: {current:.2f}% (upper: {upper:.2f}%) · sin cambios → pausa"
    add('fed', 'Fed sesgo (FRED EFFR)',
        fed_sig, fed_txt, 2, 'FRED', 'liquidez')
else:
    add('fed', 'Fed sesgo', 'r',
        'Warsh hawkish — posible subida 2026', 2, 'FRED', 'liquidez')

# 22. DXY (UUP)
r1u = pct_n(D['UUP'], 21)
if r1u is not None:
    add('dxy', 'DXY proxy (UUP)',
        'g' if r1u < -1 else ('y' if r1u < 2 else 'r'),
        f"UUP 1m: {r1u:+.1f}%", 1, 'YF', 'liquidez')

# 23. HY Spreads (FRED)
hy_df = F.get('HY', pd.DataFrame())
if len(hy_df) > 0:
    hy_v = float(hy_df['value'].iloc[-1])
    hy_d = hy_df.index[-1].strftime('%d %b')
    add('hy', 'Spreads HY crédito (FRED)',
        'g' if hy_v < 3.5 else ('y' if hy_v < 5 else 'r'),
        f"HY OAS: {hy_v:.2f}% ({hy_v*100:.0f}pb) · {hy_d}", 2, 'FRED', 'liquidez')

# ─────────────────────────────────────────────
# PUNTUACIÓN FINAL
# ─────────────────────────────────────────────

LAYERS_ORDER = [
    ('tendencia',   'Tendencia primaria',            ['sma200','mom13612','qqqxlu']),
    ('amplitud',    'Amplitud & salud interna',      ['adline','nyhl','rspspy','breadth','carlucci','fosback']),
    ('flujos',      'Flujos de riesgo & rotación',   ['xlyxlp','vwo','bnd','coppergold','tip']),
    ('macro',       'Macro & ciclo económico',       ['pmi','yieldcurve','eps']),
    ('sentimiento', 'Sentimiento de mercado',        ['vix','putcall','aaii']),
    ('liquidez',    'Liquidez & política monetaria', ['fed','dxy','hy']),
]

total_pts, total_max = 0, 0
for _, _, ids in LAYERS_ORDER:
    for iid in ids:
        if iid not in results:
            continue
        r = results[iid]
        if r['sig'] in ('n', 'loading'):
            continue
        total_max += r['w']
        if r['sig'] == 'g':   total_pts += r['w']
        elif r['sig'] == 'y': total_pts += r['w'] * 0.5

score = (total_pts / total_max * 10) if total_max > 0 else 5.0
signal = 'VERDE' if score >= 6.5 else ('ROJO' if score < 3.5 else 'AMARILLO')
signal_emoji = '🟢' if score >= 6.5 else ('🔴' if score < 3.5 else '🟡')
counts = {'g': 0, 'y': 0, 'r': 0, 'n': 0}
for r in results.values():
    s = r['sig']
    counts[s if s in counts else 'n'] += 1

print(f"\n{'='*50}")
print(f"  {signal_emoji}  SEMÁFORO: {signal}")
print(f"  Puntuación: {score:.1f} / 10")
print(f"  Indicadores calculados: {len(results)}/23")
print(f"  Verdes: {counts['g']} · Amarillos: {counts['y']} · Rojos: {counts['r']} · Neutros: {counts['n']}")
print(f"{'='*50}")

# ─────────────────────────────────────────────
# GENERACIÓN DEL HTML
# ─────────────────────────────────────────────

DETAILS = {
    'sma200':    'SPX vs media 200 sesiones. >+2% verde, ±2% amarillo, <-2% rojo. El filtro de tendencia más robusto del sistema.',
    'mom13612':  'Media de retornos a 1/3/6/12 meses (Keller HAA). Si todos los plazos son positivos la tendencia es sólida.',
    'qqqxlu':    'QQQ (tecnología) vs XLU (utilities). Diferencial 1m. Cuando QQQ lidera el mercado acepta valoraciones growth altas.',
    'adline':    '% de ETFs sectoriales cotizando por encima de su SMA50. Proxy robusto de la amplitud de mercado.',
    'nyhl':      'IWM (small caps) vs SPY (large caps) retorno 3m. Cuando small caps lideran la amplitud es genuina y el mercado es sano.',
    'rspspy':    'S&P 500 equiponderado vs capitalización. Si RSP se queda atrás el rally lo sostienen pocas mega-caps — fragilidad.',
    'breadth':   'Proxy del Breadth Thrust de Zweig: % ETFs alcistas pasando de <40% a >61% rápidamente. Señal de convicción institucional.',
    'carlucci':  'Proxy Carlucci: % ETFs sectoriales sobre su SMA200. Umbral 65%. Por encima = salud interna del mercado sólida.',
    'fosback':   'Proxy Fosback: dispersión de retornos sectoriales 1m. Baja dispersión = mercado coherente. Alta = incoherencia interna.',
    'xlyxlp':    'Consumo discrecional vs básico. Mide apetito por riesgo económico. Divergencia con el índice es señal de alerta.',
    'vwo':       'Canario sistémico. Emergentes caen antes que el S&P 500 por ser el eslabón más débil de la cadena de riesgo global.',
    'bnd':       'Canario de renta fija. BND cayendo con S&P subiendo = bonistas descuentan algo que acciones aún ignoran.',
    'coppergold':'Ratio cobre (crecimiento) vs oro (refugio). Uno de los mejores adelantados del ciclo macro a 3 meses.',
    'tip':       'Canario de Wouter Keller (HAA). Momentum 13612U del ETF TIP. Negativo = rotar todo a defensivos.',
    'pmi':       'ISM PMI manufacturero USA (FRED). >52 expansión sólida, 50-52 frágil, <50 contracción. Adelanta el ciclo 2-3 meses.',
    'yieldcurve':'Spread 2Y-10Y de Treasuries. Inversión precede recesiones 6-18 meses. Desinvirtiéndose = señal positiva de transición.',
    'eps':       'Proxy de beneficios: aceleración del SPY vs su tendencia de 6 meses. Positiva = empresas sorprendiendo al alza.',
    'vix':       'Índice VIX: volatilidad implícita S&P 500. <18 favorable, 18-28 nerviosismo, >28 pánico (señal contraria alcista).',
    'putcall':   'Ratio VIX/VIX3M: curva de volatilidad. Backwardation (>1.05) = estrés de corto plazo. Contango (<0.9) = mercado tranquilo.',
    'aaii':      'Fear & Greed Index (alternative.me). <35 miedo extremo = contrarian alcista. >70 codicia extrema = precaución.',
    'fed':       'Tendencia del tipo efectivo Fed Funds (FRED). Subiendo = restrictivo. Bajando = expansivo. Sin cambios = pausa.',
    'dxy':       'Proxy DXY via ETF UUP. Dólar fuerte presiona emergentes y beneficios de multinacionales americanas.',
    'hy':        'ICE BofA HY OAS (FRED). Los spreads se amplían antes de que caiga la bolsa. Radar del riesgo de crédito sistémico.',
}

DOT = {'g': '#3B6D11', 'y': '#BA7517', 'r': '#A32D2D', 'n': '#888780'}
SIG_COLOR = {'VERDE': '#3B6D11', 'AMARILLO': '#854F0B', 'ROJO': '#A32D2D'}[signal]
VERDICT   = {'VERDE': 'Riesgo ON — exposición plena recomendada',
             'AMARILLO': 'Cautela táctica — reducir exposición al 50-70%',
             'ROJO': 'Riesgo OFF — rotar a bonos / liquidez'}[signal]
BAR_PCT   = score * 10
BAR_COL   = '#3B6D11' if score >= 6.5 else ('#A32D2D' if score < 3.5 else '#BA7517')

canary_red    = any(results.get(k, {}).get('sig') == 'r' for k in ['bnd', 'tip', 'vwo'])
canary_alerts = [l for k, l in [('bnd','BND cediendo'),('tip','TIP Keller negativo'),('vwo','VWO cayendo')]
                 if results.get(k, {}).get('sig') == 'r']
CANARY_BG  = '#FAEEDA' if canary_red else '#EAF3DE'
CANARY_BRD = '#EF9F27' if canary_red else '#97C459'
CANARY_TC  = '#633806' if canary_red else '#27500A'
CANARY_ICO = '⚠' if canary_red else '✓'
CANARY_MSG = f"<strong>Canarios en alerta:</strong> {' · '.join(canary_alerts)}" if canary_red \
             else "<strong>Canarios sin alerta:</strong> TIP, VWO y BND sin señales de estrés sistémico."

def render_layer(layer_id, layer_title, ids):
    items_html = ''
    l_pts, l_max = 0, 0
    for iid in ids:
        if iid not in results:
            continue
        r = results[iid]
        s = r['sig']
        dc = DOT.get(s, '#888780')
        src = r.get('src', '')
        src_lbl = {'YF': 'Yahoo Finance', 'FRED': 'FRED', 'web': 'Fear&Greed', 'calc': 'cálculo'}.get(src, src)
        detail = DETAILS.get(iid, '')
        if s not in ('n', 'loading'):
            l_max += r['w']
            if s == 'g':   l_pts += r['w']
            elif s == 'y': l_pts += r['w'] * 0.5
        items_html += f'''
        <div class="irow" onclick="tog('{iid}')">
          <div class="dot" style="background:{dc}"></div>
          <span class="iname">{r['name']}</span>
          <span class="ival">{r['val']}</span>
          <span class="isrc">{src_lbl}</span>
          <span class="iw">×{r['w']}</span>
        </div>
        <div class="det" id="det-{iid}">{detail}</div>'''

    lpct = l_pts / l_max if l_max > 0 else 0.5
    lbg = '#EAF3DE' if lpct >= 0.65 else ('#FAEEDA' if lpct >= 0.35 else '#FCEBEB')
    ltc = '#27500A' if lpct >= 0.65 else ('#633806' if lpct >= 0.35 else '#791F1F')
    llbl = 'Verde' if lpct >= 0.65 else ('Amarillo' if lpct >= 0.35 else 'Rojo')
    return f'''
  <div class="lcard">
    <div class="lhdr">
      <span class="ltitle">{layer_title}</span>
      <span class="lbadge" style="background:{lbg};color:{ltc}">{llbl}</span>
    </div>
    {items_html}
  </div>'''

layers_html = ''.join(render_layer(lid, ltitle, ids) for lid, ltitle, ids in LAYERS_ORDER)

HTML = f'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Semáforo de Mercado Global · {FECHA}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f9f9f7;color:#1a1a1a;padding:24px 20px;max-width:980px;margin:0 auto}}
.top{{display:flex;align-items:center;gap:16px;margin-bottom:1.5rem;padding-bottom:1rem;border-bottom:1px solid #e5e5e0}}
.sig{{width:76px;height:76px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:30px;flex-shrink:0;background:{SIG_COLOR}}}
.top-info{{flex:1}}
h1{{font-size:18px;font-weight:600;margin-bottom:2px}}
.sub{{font-size:11px;color:#888780;margin-bottom:5px}}
.verdict{{font-size:13px;font-weight:500;color:{SIG_COLOR}}}
.snum{{font-size:28px;font-weight:600;color:#1a1a1a;line-height:1;text-align:right}}
.slbl{{font-size:10px;color:#888780;text-align:right;margin-top:1px}}
.bar-bg{{height:9px;background:#e5e5e0;border-radius:5px;overflow:hidden;margin-bottom:4px}}
.bar-fill{{height:100%;border-radius:5px;width:{BAR_PCT:.0f}%;background:{BAR_COL}}}
.bar-lbls{{display:flex;justify-content:space-between;font-size:10px;color:#888780;margin-bottom:1rem}}
.mgrid{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:1rem}}
.mc{{background:#f3f4f6;border-radius:8px;padding:8px 10px;text-align:center}}
.mc .mv{{font-size:18px;font-weight:500}}.mc .ml{{font-size:10px;color:#888780;margin-top:1px}}
.badge{{background:#dcfce7;color:#166534;font-size:10px;padding:3px 10px;border-radius:4px;border:1px solid #86efac;margin-bottom:1rem;display:inline-flex;align-items:center;gap:5px}}
.canary{{padding:8px 12px;border-radius:8px;margin-bottom:1rem;display:flex;align-items:center;gap:8px;font-size:11px;line-height:1.5;background:{CANARY_BG};border:1px solid {CANARY_BRD};color:{CANARY_TC}}}
.layers{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:10px;margin-bottom:1.5rem}}
.lcard{{background:#fff;border:1px solid #e5e5e0;border-radius:12px;padding:14px 18px}}
.lhdr{{display:flex;align-items:center;margin-bottom:8px}}
.ltitle{{font-size:12px;font-weight:600;flex:1}}
.lbadge{{font-size:10px;font-weight:500;padding:2px 7px;border-radius:6px}}
.irow{{display:flex;align-items:center;gap:7px;padding:5px 0;border-top:1px solid #f3f4f6;cursor:pointer}}
.irow:hover{{background:#f9f9f7;margin:0 -18px;padding-left:18px;padding-right:18px;border-radius:4px}}
.dot{{width:8px;height:8px;border-radius:50%;flex-shrink:0}}
.iname{{font-size:11px;flex:1;line-height:1.3}}
.ival{{font-size:10px;color:#6b7280;text-align:right;max-width:150px;line-height:1.2}}
.isrc{{font-size:9px;padding:1px 5px;border-radius:3px;margin-left:3px;flex-shrink:0;background:#f3f4f6;color:#6b7280}}
.iw{{font-size:9px;color:#aaa;min-width:16px;text-align:right}}
.det{{background:#f9f9f7;border-radius:6px;padding:8px 10px;margin-top:4px;font-size:10px;color:#6b7280;line-height:1.7;display:none;border-left:2px solid #e5e5e0}}
.det.open{{display:block}}
.footer{{font-size:10px;color:#888780;text-align:center;padding-top:1rem;border-top:1px solid #e5e5e0}}
@media(max-width:600px){{
  .top{{flex-wrap:wrap}}.mgrid{{grid-template-columns:repeat(2,1fr)}}
}}
</style>
</head>
<body>
<div class="top">
  <div class="sig">{signal_emoji}</div>
  <div class="top-info">
    <h1>Semáforo de mercado global</h1>
    <div class="sub">Actualizado el {FECHA} · Yahoo Finance + FRED + Fear&Greed · 6 capas · {len(results)} indicadores · horizonte 1-3 meses</div>
    <div class="verdict">{signal} — {VERDICT}</div>
  </div>
  <div>
    <div class="snum">{score:.1f}</div>
    <div class="slbl">/ 10</div>
  </div>
</div>

<div class="bar-bg"><div class="bar-fill"></div></div>
<div class="bar-lbls">
  <span>🔴 Rojo (0)</span>
  <span style="color:#1a1a1a;font-weight:500">Rojo &lt;3.5 · Amarillo 3.5-6.5 · Verde &gt;6.5</span>
  <span>🟢 Verde (10)</span>
</div>

<div class="mgrid">
  <div class="mc"><div class="mv" style="color:#3B6D11">{counts['g']}</div><div class="ml">Verdes</div></div>
  <div class="mc"><div class="mv" style="color:#854F0B">{counts['y']}</div><div class="ml">Amarillos</div></div>
  <div class="mc"><div class="mv" style="color:#A32D2D">{counts['r']}</div><div class="ml">Rojos</div></div>
  <div class="mc"><div class="mv" style="color:#3B6D11">{counts['n']}</div><div class="ml">Neutros</div></div>
</div>

<div class="badge">✦ 100% gratuito · sin API key · actualización automática cada sábado</div>
<div class="canary">{CANARY_ICO} {CANARY_MSG}</div>

<div class="layers">{layers_html}</div>

<div class="footer">
  Fuentes: Yahoo Finance · FRED (St. Louis Fed) · Fear &amp; Greed Index (alternative.me) · 100% gratuito<br>
  Haz clic en cada indicador para ver su interpretación · Orientativo, no constituye asesoramiento financiero<br>
  Actualización automática cada sábado a las 07:00h UTC
</div>

<script>
function tog(id){{
  const el=document.getElementById('det-'+id);
  if(el) el.classList.toggle('open');
}}
</script>
</body>
</html>'''

output_path = os.path.join(os.path.dirname(__file__), '..', 'docs', 'index.html')
os.makedirs(os.path.dirname(output_path), exist_ok=True)
with open(output_path, 'w', encoding='utf-8') as f:
    f.write(HTML)

print(f"\n✓ HTML generado: docs/index.html ({len(HTML):,} chars)")
print(f"✓ Señal: {signal_emoji} {signal} · {score:.1f}/10")
