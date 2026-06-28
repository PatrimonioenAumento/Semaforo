"""
Semáforo de Mercado Global — versión sin API key
23 indicadores · 6 capas · horizonte 1-3 meses
Fuentes: Yahoo Finance · FRED · CNN Fear & Greed · cálculo propio
"""

import yfinance as yf
import pandas as pd
import numpy as np
import requests
import json
import os
import warnings
from datetime import datetime
from io import StringIO

warnings.filterwarnings('ignore')

FRED_BASE = 'https://fred.stlouisfed.org/graph/fredgraph.csv?id='
FECHA = datetime.now().strftime("%d %b %Y %H:%M")

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

def download_fred(series_id):
    try:
        url = f"{FRED_BASE}{series_id}"
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        df = pd.read_csv(StringIO(r.text), parse_dates=['DATE'], index_col='DATE')
        df = df.replace('.', np.nan).dropna()
        df[series_id] = df[series_id].astype(float)
        return df
    except Exception as e:
        print(f"  ✗ FRED {series_id}: {e}")
        return pd.DataFrame()

def pct_n(s, n):
    if len(s) < n + 1:
        return None
    return (float(s.iloc[-1]) / float(s.iloc[-(n + 1)]) - 1) * 100

def sma(s, n):
    if len(s) < n:
        return None
    return float(s.iloc[-n:].mean())

def mom13612u(s):
    if len(s) < 253:
        return None
    vals = [pct_n(s, d) for d in [21, 63, 126, 252]]
    if any(v is None for v in vals):
        return None
    return sum(vals) / 4

def fetch_cnn_fear_greed():
    """CNN Fear & Greed Index — API pública sin autenticación"""
    try:
        url = 'https://production.dataviz.cnn.io/index/fearandgreed/graphdata'
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        score = data['fear_and_greed']['score']
        rating = data['fear_and_greed']['rating']
        return float(score), rating
    except Exception as e:
        print(f"  ✗ CNN Fear&Greed: {e}")
        return None, None

def fetch_fed_rate_fred():
    """Tipo efectivo Fed Funds vs. último dato disponible en FRED"""
    try:
        # Tipo efectivo actual
        df_rate = download_fred('EFFR')
        # Tipo objetivo superior (upper bound)
        df_upper = download_fred('DFEDTARU')
        if len(df_rate) == 0 or len(df_upper) == 0:
            return None
        current = float(df_rate.iloc[-1].iloc[0])
        upper = float(df_upper.iloc[-1].iloc[0])
        return {'current': current, 'upper': upper}
    except Exception as e:
        print(f"  ✗ Fed FRED: {e}")
        return None

# ─────────────────────────────────────────────
# DESCARGA DE DATOS
# ─────────────────────────────────────────────

print("Descargando Yahoo Finance...")
TICKERS = {
    'SPX':   '^GSPC',  'QQQ':   'QQQ',    'XLU':   'XLU',
    'RSP':   'RSP',    'XLY':   'XLY',    'XLP':   'XLP',
    'VWO':   'VWO',    'BND':   'BND',    'TIP':   'TIP',
    'CPER':  'CPER',   'GLD':   'GLD',    'UUP':   'UUP',
    'VIX':   '^VIX',   'PCALL': '^PCALL', 'OEXA':  '^OEXA200R',
    'NYADV': '^NYADV', 'NYDEC': '^NYDEC', 'NYHGH': '^NYHGH',
    'NYLOW': '^NYLOW', 'TRIN':  '^TRIN',
}
D = {}
for k, t in TICKERS.items():
    D[k] = download_yf(t)
    status = f"{len(D[k])} sesiones" if len(D[k]) > 0 else "sin datos"
    print(f"  {'✓' if len(D[k]) > 0 else '✗'} {t}: {status}")

print("\nDescargando FRED...")
FRED_IDS = {'HY': 'BAMLH0A0HYM2', 'CURVE': 'T10Y2Y', 'PMI': 'NAPM'}
F = {}
for k, sid in FRED_IDS.items():
    F[k] = download_fred(sid)
    status = f"{len(F[k])} obs" if len(F[k]) > 0 else "sin datos"
    print(f"  {'✓' if len(F[k]) > 0 else '✗'} {sid}: {status}")

print("\nDescargando datos alternativos gratuitos...")
cnn_score, cnn_rating = fetch_cnn_fear_greed()
if cnn_score:
    print(f"  ✓ CNN Fear&Greed: {cnn_score:.0f} ({cnn_rating})")
fed_data = fetch_fed_rate_fred()
if fed_data:
    print(f"  ✓ Fed Funds rate: {fed_data['current']:.2f}% (upper bound: {fed_data['upper']:.2f}%)")

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

# 4. A/D line + Breadth Thrust
adv, dec = D['NYADV'], D['NYDEC']
n = min(len(adv), len(dec))
if n >= 10:
    rats = []
    for i in range(max(0, n-30), n):
        a, b = float(adv.iloc[i]), float(dec.iloc[i])
        if a + b > 0:
            rats.append(a / (a + b))
    avg10 = np.mean(rats[-10:]) * 100
    add('adline', 'A/D line NYSE',
        'g' if avg10 > 55 else ('y' if avg10 > 45 else 'r'),
        f"A/D ratio 10d: {avg10:.1f}%", 2, 'YF', 'amplitud')
    bt = any(
        any(r < 0.40 for r in rats[i:i+10]) and rats[min(i+9, len(rats)-1)] > 0.615
        for i in range(len(rats) - 9)
    )
    add('breadth', 'Breadth Thrust Zweig',
        'g' if bt else 'n',
        'Señal activa detectada' if bt else 'Sin señal activa (neutro)',
        2, 'calc', 'amplitud')

# 5. NYHL + Fosback
hgh, low = D['NYHGH'], D['NYLOW']
n2 = min(len(hgh), len(low))
if n2 >= 10:
    nets = [float(hgh.iloc[i]) - float(low.iloc[i]) for i in range(max(0, n2-10), n2)]
    avg_nyhl = np.mean(nets)
    add('nyhl', 'NYHL neto suavizado 10d',
        'g' if avg_nyhl > 100 else ('y' if avg_nyhl > 0 else 'r'),
        f"NYHL neto 10d: {avg_nyhl:+.0f}", 2, 'YF', 'amplitud')
    hR = float(hgh.iloc[-1]) / 3000
    lR = float(low.iloc[-1]) / 3000
    fosb = min(hR, lR) * 100
    add('fosback', 'Fosback High-Low Logic',
        'g' if fosb < 1 else ('y' if fosb < 2.5 else 'r'),
        f"Fosback: {fosb:.2f}% ({'coherente' if fosb < 1 else 'moderado' if fosb < 2.5 else 'incoherente'})",
        1, 'calc', 'amplitud')

# 6. RSP/SPY
r3r, r3s = pct_n(D['RSP'], 63), pct_n(spx, 63)
if r3r and r3s:
    d = r3r - r3s
    add('rspspy', 'RSP/SPY (concentración)',
        'g' if d > 1 else ('y' if d > -3 else 'r'),
        f"RSP vs SPY 3m: {d:+.1f}%", 1, 'YF', 'amplitud')

# 7. TRIN
trin = D['TRIN']
if len(trin) >= 10:
    avg_t = float(trin.iloc[-10:].mean())
    add('trin', 'TRIN-10 Arms Index',
        'g' if avg_t < 0.9 else ('y' if avg_t < 1.2 else 'r'),
        f"TRIN-10: {avg_t:.2f}", 1, 'YF', 'amplitud')

# 8. Carlucci
oexa = D['OEXA']
if len(oexa) >= 22:
    lo = float(oexa.iloc[-1])
    m1o = pct_n(oexa, 21) or 0
    add('carlucci', 'Carlucci $OEXA200R',
        'g' if (lo >= 65 and m1o > 0) else ('y' if lo >= 55 else 'r'),
        f"$OEXA200R: {lo:.1f}% (umbral 65%) | 1m: {m1o:+.1f}%", 2, 'YF', 'amplitud')

# 9. XLY/XLP
r1y, r1p = pct_n(D['XLY'], 21), pct_n(D['XLP'], 21)
if r1y and r1p:
    d = r1y - r1p
    add('xlyxlp', 'XLY/XLP (ciclo vs defensivo)',
        'g' if d > 2 else ('y' if d > -2 else 'r'),
        f"XLY vs XLP 1m: {d:+.1f}%", 2, 'YF', 'flujos')

# 10. VWO
r1v, r3v = pct_n(D['VWO'], 21), pct_n(D['VWO'], 63)
if r1v is not None:
    add('vwo', 'VWO canario emergentes',
        'g' if (r1v > 0 and (r3v or 0) > 0) else ('r' if r1v < -3 else 'y'),
        f"VWO 1m: {r1v:+.1f}%{f' | 3m: {r3v:+.1f}%' if r3v else ''}", 2, 'YF', 'flujos')

# 11. BND
r1b = pct_n(D['BND'], 21)
if r1b is not None:
    add('bnd', 'BND canario renta fija',
        'g' if r1b > 0 else ('y' if r1b > -1 else 'r'),
        f"BND 1m: {r1b:+.1f}%", 2, 'YF', 'flujos')

# 12. Copper/Gold
r1c, r1g = pct_n(D['CPER'], 21), pct_n(D['GLD'], 21)
if r1c and r1g:
    d = r1c - r1g
    add('coppergold', 'Copper/Gold ratio',
        'g' if d > 2 else ('y' if d > -2 else 'r'),
        f"CPER vs GLD 1m: {d:+.1f}%", 2, 'YF', 'flujos')

# 13. TIP Keller
m_tip = mom13612u(D['TIP'])
if m_tip is not None:
    add('tip', 'TIP momentum (Keller)',
        'g' if m_tip > 0.5 else ('y' if m_tip > -0.5 else 'r'),
        f"TIP 13612U: {m_tip:+.2f}% (Keller HAA)", 2, 'YF', 'flujos')

# 14. PMI (FRED)
if len(F['PMI']) > 0:
    pmi_v = float(F['PMI'].iloc[-1].iloc[0])
    pmi_d = F['PMI'].index[-1].strftime('%b %Y')
    add('pmi', 'ISM PMI manufacturero USA',
        'g' if pmi_v > 52 else ('y' if pmi_v > 50 else 'r'),
        f"ISM PMI: {pmi_v:.1f} ({pmi_d})", 2, 'FRED', 'macro')

# 15. Curva 2Y-10Y (FRED)
if len(F['CURVE']) > 0:
    yc_v = float(F['CURVE'].iloc[-1].iloc[0])
    yc_d = F['CURVE'].index[-1].strftime('%d %b')
    add('yieldcurve', 'Curva 2Y-10Y USA',
        'g' if yc_v > 0.25 else ('y' if yc_v > -0.25 else 'r'),
        f"2Y-10Y: {yc_v:+.2f}% ({yc_v*100:+.0f}pb) · {yc_d}", 2, 'FRED', 'macro')

# 16. HY Spreads (FRED)
if len(F['HY']) > 0:
    hy_v = float(F['HY'].iloc[-1].iloc[0])
    hy_d = F['HY'].index[-1].strftime('%d %b')
    add('hy', 'Spreads HY crédito',
        'g' if hy_v < 3.5 else ('y' if hy_v < 5 else 'r'),
        f"HY OAS: {hy_v:.2f}% ({hy_v*100:.0f}pb) · {hy_d}", 2, 'FRED', 'liquidez')

# 17. VIX
if len(D['VIX']) > 0:
    v = float(D['VIX'].iloc[-1])
    add('vix', 'VIX (fear gauge)',
        'g' if v < 18 else ('y' if v < 28 else 'r'),
        f"VIX: {v:.2f}", 2, 'YF', 'sentimiento')

# 18. Put/Call
if len(D['PCALL']) > 0:
    pc = float(D['PCALL'].iloc[-1])
    add('putcall', 'Put/Call ratio CBOE',
        'g' if pc < 0.9 else ('y' if pc < 1.2 else 'r'),
        f"Put/Call CBOE: {pc:.2f}", 1, 'YF', 'sentimiento')

# 19. CNN Fear & Greed (proxy AAII)
if cnn_score is not None:
    # <25 miedo extremo = contrarian alcista, 25-45 miedo, 45-55 neutro, 55-75 codicia, >75 codicia extrema
    sig = 'g' if cnn_score < 35 else ('r' if cnn_score > 70 else 'y')
    add('aaii', 'CNN Fear & Greed Index',
        sig,
        f"Score: {cnn_score:.0f}/100 · {cnn_rating} ({'contrarian alcista' if cnn_score < 35 else 'precaución' if cnn_score > 70 else 'neutro'})",
        1, 'CNN', 'sentimiento')
else:
    add('aaii', 'CNN Fear & Greed Index',
        'y', 'Dato no disponible esta semana', 1, 'CNN', 'sentimiento')

# 20. DXY (UUP)
r1u = pct_n(D['UUP'], 21)
if r1u is not None:
    add('dxy', 'DXY proxy (UUP)',
        'g' if r1u < -1 else ('y' if r1u < 2 else 'r'),
        f"UUP 1m: {r1u:+.1f}%", 1, 'YF', 'liquidez')

# 21. Fed sesgo (FRED EFFR vs upper bound)
if fed_data:
    current = fed_data['current']
    upper = fed_data['upper']
    # Comparamos con histórico reciente para detectar tendencia
    df_upper = download_fred('DFEDTARU')
    if len(df_upper) >= 60:
        upper_6m_ago = float(df_upper.iloc[-60].iloc[0])
        if upper > upper_6m_ago:
            fed_sig = 'r'
            fed_txt = f"Fed Funds: {current:.2f}% · subiendo vs hace 3m ({upper_6m_ago:.2f}%) · restrictivo"
        elif upper < upper_6m_ago:
            fed_sig = 'g'
            fed_txt = f"Fed Funds: {current:.2f}% · bajando vs hace 3m ({upper_6m_ago:.2f}%) · expansivo"
        else:
            fed_sig = 'y'
            fed_txt = f"Fed Funds: {current:.2f}% · sin cambios · pausa"
    else:
        fed_sig = 'y'
        fed_txt = f"Fed Funds: {current:.2f}% (upper bound: {upper:.2f}%)"
    add('fed', 'Fed sesgo (FRED EFFR)',
        fed_sig, fed_txt, 2, 'FRED', 'liquidez')
else:
    add('fed', 'Fed sesgo (FRED EFFR)',
        'r', 'Warsh hawkish — posible subida 2026', 2, 'FRED', 'liquidez')

# 22. EPS proxy — SPY momentum relativo vs tendencia larga
# Si SPY supera su tendencia de 6m con aceleración, los beneficios están sorprendiendo
if len(spx) >= 200:
    r1s = pct_n(spx, 21)
    r6s = pct_n(spx, 126)
    if r1s and r6s:
        # Aceleración: el retorno reciente supera el promedio de 6m anualizado
        monthly_avg_6m = r6s / 6
        aceleracion = r1s - monthly_avg_6m
        if aceleracion > 1.5:
            eps_sig, eps_txt = 'g', f"Proxy EPS: SPY acelera {aceleracion:+.1f}% vs media 6m — beneficios sorprendiendo"
        elif aceleracion > -1.5:
            eps_sig, eps_txt = 'y', f"Proxy EPS: SPY en línea con tendencia ({aceleracion:+.1f}%) — beneficios neutros"
        else:
            eps_sig, eps_txt = 'r', f"Proxy EPS: SPY desacelera {aceleracion:+.1f}% vs media 6m — presión en beneficios"
        add('eps', 'EPS proxy (momentum SPY)',
            eps_sig, eps_txt, 2, 'calc', 'macro')

# ─────────────────────────────────────────────
# PUNTUACIÓN FINAL
# ─────────────────────────────────────────────

LAYERS_ORDER = [
    ('tendencia',   'Tendencia primaria',            ['sma200','mom13612','qqqxlu']),
    ('amplitud',    'Amplitud & salud interna',      ['adline','nyhl','rspspy','trin','breadth','carlucci','fosback']),
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
print(f"  Verdes: {counts['g']} · Amarillos: {counts['y']} · Rojos: {counts['r']} · Neutros: {counts['n']}")
print(f"{'='*50}")

# ─────────────────────────────────────────────
# GENERACIÓN DEL HTML
# ─────────────────────────────────────────────

DETAILS = {
    'sma200':    'SPX vs media 200 sesiones. >+2% verde, ±2% amarillo, <-2% rojo. El filtro de tendencia más robusto del sistema.',
    'mom13612':  'Media de retornos a 1/3/6/12 meses (Keller HAA). Si todos los plazos son positivos la tendencia es sólida.',
    'qqqxlu':    'QQQ (tecnología) vs XLU (utilities). Diferencial 1m. Cuando QQQ lidera el mercado acepta valoraciones altas.',
    'adline':    'Ratio avances/(avances+retrocesos) del NYSE, media 10 días. Los techos de mercado siempre van precedidos de deterioro en amplitud.',
    'nyhl':      'Nuevos máximos minus nuevos mínimos de 52 semanas, media 10 días. Mide convicción estructural del mercado.',
    'rspspy':    'S&P 500 equiponderado vs capitalización. Si RSP se queda atrás el rally lo sostienen pocas mega-caps.',
    'trin':      'Arms Index media 10 días. Por encima de 1 el volumen fluye a las bajadas — presión vendedora real.',
    'breadth':   'SEÑAL ESPECIAL de Marty Zweig. Solo ~20 señales desde 1950. Todas han precedido rentabilidades positivas a 12 meses.',
    'carlucci':  '% acciones del S&P 100 sobre su SMA200. Umbral crítico: 65%. Por encima con momentum positivo = mercado sano.',
    'fosback':   'min(nuevos máximos/total, nuevos mínimos/total). Penaliza coexistencia anómala de muchos máximos y mínimos simultáneos.',
    'xlyxlp':    'Consumo discrecional vs básico. Mide apetito por riesgo económico. La divergencia con el índice es la señal más valiosa.',
    'vwo':       'Canario sistémico. Emergentes caen antes que el S&P 500 por ser el eslabón más débil de la cadena de riesgo.',
    'bnd':       'Canario de renta fija. BND cayendo con S&P subiendo = bonistas descuentan algo que acciones ignoran.',
    'coppergold':'Ratio cobre (crecimiento) vs oro (refugio). Uno de los mejores adelantados del ciclo macro a 3 meses.',
    'tip':       'Canario de Wouter Keller (HAA). Momentum 13612U del ETF TIP. Negativo = rotar a defensivos.',
    'pmi':       'ISM PMI manufacturero USA. >52 expansión sólida, 50-52 frágil, <50 contracción. Adelanta el ciclo 2-3 meses.',
    'yieldcurve':'Spread 2Y-10Y de Treasuries. Inversión precede recesiones 6-18 meses. Desinvirtiéndose = señal positiva.',
    'eps':       'Proxy de momentum de beneficios: aceleración del SPY vs su tendencia de 6 meses. Sin coste de API externa.',
    'vix':       'Índice VIX: volatilidad implícita S&P 500. <18 favorable, 18-28 nerviosismo, >28 pánico (señal contraria alcista).',
    'putcall':   'Ratio put/call CBOE. <0.9 neutral/alcista. >1.2 miedo extremo = señal contraria alcista.',
    'aaii':      'CNN Fear & Greed Index (proxy sentimiento). <35 miedo = contrarian alcista. >70 codicia = precaución. Gratuito y diario.',
    'fed':       'Tendencia del tipo efectivo Fed Funds (FRED). Subiendo = restrictivo (rojo). Bajando = expansivo (verde). Sin API externa.',
    'dxy':       'Proxy DXY via ETF UUP. Dólar fuerte presiona emergentes y beneficios de multinacionales.',
    'hy':        'ICE BofA HY OAS (FRED). Spreads se amplían antes de que caiga la bolsa. Radar del riesgo de crédito.',
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
        src_lbl = {'YF': 'Yahoo Finance', 'FRED': 'FRED', 'CNN': 'CNN', 'calc': 'cálculo'}.get(src, src)
        src_style = 'background:#f3f4f6;color:#6b7280'
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
          <span class="isrc" style="{src_style}">{src_lbl}</span>
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
<meta name="description" content="Semáforo de mercado global con 23 indicadores. Señal: {signal} ({score:.1f}/10). Actualización automática semanal.">
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
  .top{{flex-wrap:wrap}}.sig{{width:60px;height:60px;font-size:24px}}
  .mgrid{{grid-template-columns:repeat(2,1fr)}}
}}
</style>
</head>
<body>
<div class="top">
  <div class="sig">{signal_emoji}</div>
  <div class="top-info">
    <h1>Semáforo de mercado global</h1>
    <div class="sub">Actualizado el {FECHA} · Yahoo Finance + FRED + CNN Fear&Greed · 6 capas · 23 indicadores · horizonte 1-3 meses</div>
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
  Fuentes: Yahoo Finance · FRED (St. Louis Fed) · CNN Fear &amp; Greed Index · 100% gratuito sin registro<br>
  Haz clic en cualquier indicador para ver su interpretación · Este semáforo es orientativo y no constituye asesoramiento financiero<br>
  Generado automáticamente cada sábado a las 07:00h UTC
</div>

<script>
function tog(id){{
  const el = document.getElementById('det-'+id);
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
