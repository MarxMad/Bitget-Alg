# 3 · Datos y backtest

Tiempo: unos 30 minutos. **No necesitas API key**: todo usa datos públicos.

Un **backtest** simula una estrategia sobre precios pasados para estimar cómo le habría ido. El objetivo de esta guía no es encontrar una estrategia ganadora: es aprender a **no engañarte** con un backtest.

## 1. Anatomía de un bot

```
 datos  →  señal  →  riesgo  →  ejecución  →  monitoreo
 velas     ¿compro?   ¿cuánto?   orden en      ¿sigue vivo?
           ¿vendo?    ¿stop?     el exchange   ¿cuánto pierde?
```

Todas las estrategias del repo siguen ese flujo. El backtest prueba las tres primeras piezas; la [guía 5](05-despliegue.md) agrega las dos últimas.

## 2. Descarga velas de Bitget

```bash
python herramientas/descargar_datos.py --symbols BTCUSDT,ETHUSDT,XLMUSDT --interval 1h --days 360
```

Se guardan en `data/bitget/BTCUSDT_1H.csv`, etc. Cada fila es una vela: tiempo, apertura, máximo, mínimo, cierre y volumen.

Otras opciones:

```bash
python herramientas/descargar_datos.py --top 30 --interval 1h --days 360   # los 30 con más volumen
python herramientas/descargar_datos.py --symbols SOLUSDT --interval 1m --days 14
```

## 3. Tu primer backtest: cruce de medias

Regla: si la media rápida (EMA 12) está arriba de la lenta (EMA 48), estás **largo**; si está abajo, **corto**.

```bash
python strategies/trend_following/backtest.py data/bitget/XLMUSDT_1H.csv
```

Resultado real (XLM, 360 días, comisión taker 0.06 % por lado):

```
FULL:        net=  -0.0%  Sharpe~=+0.40  maxDD= -58.4%  trades=212
TRAIN (66%): net= -43.5%  Sharpe~=-0.87  maxDD= -56.3%  trades=143
TEST  (34%): net= +76.4%  Sharpe~=+2.22  maxDD= -33.2%  trades=69
```

**Lee esto con calma.** La misma regla perdió 43 % en los primeros 8 meses y ganó 76 % en los últimos 4. Si solo hubieras visto el periodo de prueba, creerías que encontraste una mina de oro.

Prueba variantes:

```bash
python strategies/trend_following/backtest.py data/bitget/XLMUSDT_1H.csv --fast 12 --slow 100
python strategies/trend_following/backtest.py data/bitget/XLMUSDT_1H.csv --fee 0.0002   # comisión maker
python strategies/trend_following/backtest.py data/bitget/XLMUSDT_1H.csv --optimize      # barrido de parámetros
```

## 4. Las tres trampas del backtest

| Trampa | Qué pasa | Cómo la evita el repo |
|---|---|---|
| **Comisiones** | Una estrategia que opera mucho regala su ganancia al exchange. Con comisión taker (0.06 %) la reversión a la media pasa de +18 % a −40 %. | Todos los backtests cobran comisión por defecto. |
| **Sobreajuste** | Si pruebas 100 parámetros, alguno gana por suerte. | Se separa *train* (para elegir) de *test* (para medir). |
| **Cambio de régimen** | Lo que funcionó 60 días deja de funcionar. Caso real: reversión a la media en XLM, **+18 % en 60 días, −49 % en 360**. | Probar periodos largos y walk-forward. |

## 5. ¿Mi resultado es suerte? (avanzado)

```bash
python herramientas/scan_edges.py --interval 1H          # prueba 4 familias en todos los activos descargados
python herramientas/significance_check.py                # repite el escaneo con datos barajados (sin señal)
python herramientas/walkforward.py --interval 1H         # entrena 90 días, prueba 30, avanza y repite
```

`significance_check` hace la pregunta clave: si corro el mismo filtro sobre precios **barajados** (sin ninguna señal real), ¿cuántos "ganadores" salen? En este repo, el escaneo real dio 11 ganadores y el azar dio 13.6 en promedio:

```
⚠️  El resultado real NO se distingue del azar.
```

La única estrategia que sí se separó del azar es el [cross-sectional momentum](../strategies/cross_sectional/):

```bash
python strategies/cross_sectional/research.py --majors
```

## Reto

Elige un activo, descarga sus datos y encuentra una configuración de `trend_following` que sea positiva **en train y en test** con comisión taker. Anota cuántas probaste antes de encontrarla: ese número importa tanto como el resultado.

← [2 · Tu API key demo](02-api-key-demo.md) · Siguiente: [4 · Catálogo de estrategias →](04-estrategias.md)
