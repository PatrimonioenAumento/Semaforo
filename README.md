# 🚦 Semáforo de Mercado Global

Dashboard automático con **23 indicadores** en **6 capas** para determinar si el mercado global es favorable o desfavorable para inversión. Actualización automática cada sábado a las 07:00h.

**→ [Ver el semáforo en vivo](https://TU-USUARIO.github.io/semaforo-mercado)**

## Señal actual
Se actualiza cada sábado automáticamente. Escala 0-10:
- 🟢 **Verde (>6.5):** Riesgo ON — exposición plena
- 🟡 **Amarillo (3.5-6.5):** Cautela táctica — exposición reducida
- 🔴 **Rojo (<3.5):** Riesgo OFF — rotar a bonos/liquidez

Las 6 capas
Capa	Indicadores	Fuente
Tendencia primaria	SMA200, Momentum 13612U, QQQ/XLU	Yahoo Finance
Amplitud & salud interna	A/D line, NYHL, RSP/SPY, TRIN, Breadth Thrust, Carlucci, Fosback	Yahoo Finance
Flujos de riesgo	XLY/XLP, VWO, BND, Copper/Gold, TIP Keller	Yahoo Finance
Macro & ciclo	ISM PMI, Curva 2Y-10Y, EPS surprise FactSet	FRED + Claude AI
Sentimiento	VIX, Put/Call CBOE, AAII	Yahoo Finance + Claude AI
Liquidez & política monetaria	Fed sesgo FOMC, DXY, HY spreads	Claude AI + FRED
Configuración (5 pasos)
1. Fork este repositorio
Haz clic en Fork arriba a la derecha en GitHub.
2. Activar GitHub Pages
Ve a Settings → Pages
Source: Deploy from a branch
Branch: main · Folder: /docs
Guarda. En 2 minutos tendrás tu URL: `https://TU-USUARIO.github.io/semaforo-mercado`
3. Añadir tu API key de Anthropic
Ve a Settings → Secrets and variables → Actions
Clic en New repository secret
Name: `ANTHROPIC_API_KEY`
Value: tu API key de Anthropic (`sk-ant-...`)
Guarda
4. Activar GitHub Actions
Ve a la pestaña Actions
Si te pide activar workflows, acepta
El semáforo se ejecutará automáticamente cada sábado a las 07:00h UTC
5. Primera ejecución manual
En Actions → Actualizar Semáforo de Mercado
Clic en Run workflow para generar el primer HTML
Ejecución local
```bash
git clone https://github.com/TU-USUARIO/semaforo-mercado.git
cd semaforo-mercado
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
python src/semaforo.py
# Abre docs/index.html en tu navegador
```
Fuentes de datos
Indicador	Fuente	Coste
20 indicadores de precio	Yahoo Finance	Gratuito
ISM PMI, Curva 2Y-10Y, HY spreads	FRED (St. Louis Fed)	Gratuito
EPS FactSet, AAII, Fed sesgo	Claude AI (Anthropic)	~$0.05/semana
Coste total estimado: <$3/año solo por las llamadas a Claude API.
Disclaimer
Este semáforo es orientativo y no constituye asesoramiento financiero. Elaborado con fines educativos.
