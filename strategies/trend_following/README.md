# Trend-Following / Momentum

> **Hipótesis:** ETH tiende (movimientos direccionales sostenidos). En vez de
> pelear la tendencia (como hace la reversión), la **montamos**: comprar fuerza,
> vender debilidad. Es lo opuesto a la reversión a la media.

## Señal
Cruce de medias móviles exponenciales (EMA rápida vs lenta) sobre un timeframe
alto (1h/4h) para reducir el ruido y el costo de comisiones:
- EMA_rápida > EMA_lenta → **largo**
- EMA_rápida < EMA_lenta → **corto**

Variantes a explorar: banda de separación mínima (anti-whipsaw), filtro de fuerza
de tendencia (slope/ADX), salida por stop ATR.

## Enemigos
- **Whipsaw**: en mercados laterales, la tendencia falsa genera muchos trades perdedores.
- **Comisiones**: cada flip cuesta. Por eso operamos en TF alto (menos flips).
  Entradas a mercado → fee **taker** (0.06%).

## Estado
🟡 **Optimizada y validada en backtest.** Backtester vectorizado con barrido
train/test; el bot en vivo queda como ejercicio. Resultados y config validada en
[`RESULTS.md`](RESULTS.md). Edge robusto en XLM, no en ETH.

## Archivos
| Archivo | Rol |
|---|---|
| `core.py` | Señal vectorizada (`compute_position`) + `vol_target` (sizing) |
| `backtest.py` | Backtester + `--optimize` (barrido con train/test) |
| `RESULTS.md` | Resultados 360d + polish (vol-target) |

## Uso
```bash
# 0. Datos de Bitget (1m, para poder resamplear a 1h/4h)
python herramientas/descargar_datos.py --symbols XLMUSDT --interval 1m --days 360

# 1. Optimizar / re-validar
python strategies/trend_following/backtest.py data/bitget/XLMUSDT_1m.csv --optimize

# 2. Backtest de la config pulida
python strategies/trend_following/backtest.py data/bitget/XLMUSDT_1m.csv \
  --tf 1h --fast 12 --slow 100 --min-sep 0.01 --vol-target 0.006 --max-lev 1.5
```
