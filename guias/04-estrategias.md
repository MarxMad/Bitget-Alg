# 4 · Catálogo de estrategias

Cada estrategia vive en su carpeta dentro de `strategies/`, con su código, su README y sus resultados. Los comandos se corren desde la raíz del repo con el entorno activo.

**Leyenda:** ✅ con ventaja medible · 🟡 funciona con matices · ❌ sin ventaja después de comisiones · 📝 idea sin implementar

---

## ✅ Cross-sectional momentum · Bitget

`strategies/cross_sectional/`

Ordena 12 criptos grandes por su rendimiento de los últimos 7 días. Compra las 3 más fuertes y vende en corto las 3 más débiles, en montos iguales, y rebalancea cada 24 h. No adivina si el mercado sube o baja: apuesta a que la fuerza **relativa** persiste unos días.

Es la única estrategia del repo que superó la prueba contra datos barajados.

```bash
python strategies/cross_sectional/research.py --majors            # backtest y barrido de parámetros
python strategies/cross_sectional/research.py --majors --shuffle  # la misma prueba sobre azar
python -m strategies.cross_sectional.strategy --once              # un ciclo en papel (requiere .env)
```

En producción corre una vez al día con GitHub Actions o Vercel (ver [guía 5](05-despliegue.md)).

## 🟡 Market maker por volatilidad · Bitget

`strategies/mm_bitget/`

Pone una orden de compra y otra de venta alrededor del precio, a 2.5 veces la volatilidad de 1 minuto del activo, y las reacomoda cada 15 s. Todas las órdenes son *post-only* (nunca toma liquidez). Calcula el tamaño de las órdenes a partir de tu saldo.

Con ancho 2.5x queda en **breakeven**: genera volumen sin perder en promedio. Con 3.0x gana un poco y genera menos volumen.

```bash
python strategies/mm_bitget/backtest.py                      # backtest sobre velas de 1m
python strategies/mm_bitget/optimize.py --symbols XLMUSDT     # busca el ancho óptimo (train/test)
python strategies/mm_bitget/preflight.py                      # revisa cuenta, saldo y permisos
python -m strategies.mm_bitget.strategy --once                # un ciclo en papel (requiere .env)
```

¿Por qué no un spread fijo? Un market maker que cotiza a ±0.02 % fijo queda lejos del mejor precio en BTC, solo se llena cuando el precio lo atraviesa y pierde ~0.03 % de cada dólar operado. Puedes comprobarlo:

```bash
python strategies/mm_bitget/replay_fixed_spread.py --symbol XLMUSDT
```

## 🟡 Trend-following (cruce de EMAs) · Bitget

`strategies/trend_following/`

Largo cuando la EMA rápida está arriba de la lenta; corto cuando está abajo. Es la estrategia de la [guía 3](03-datos-y-backtest.md). En XLM, 22 de 96 configuraciones fueron positivas en train **y** en test; en ETH solo 3.

```bash
python strategies/trend_following/backtest.py data/bitget/XLMUSDT_1H.csv --optimize
```

Por ahora es solo backtest: convertirla en bot (con `shared/config.py → client_from_env()`) es un buen ejercicio después del taller.

## ❌ Momentum multi-timeframe · Bitget

`strategies/momentum_mtf/`

Filtra la dirección con un timeframe alto (4h/1d) y entra con uno bajo (1h). La idea es buena, pero en ETH ninguna configuración generalizó (0 de 36).

```bash
python strategies/momentum_mtf/backtest.py data/bitget/ETHUSDT_1H.csv --optimize
```

## 📝 Ideas para implementar

Cada una tiene un README con la hipótesis y los riesgos. Son buenos proyectos después del taller.

| Carpeta | Idea |
|---|---|
| `funding_carry/` | Cobrar el *funding rate* de los perpetuos, cubriendo el riesgo de precio. |
| `pairs_eth_btc/` | Operar el ratio ETH/BTC cuando se aleja de su media. |
| `volatility_breakout/` | Entrar cuando el precio rompe un rango con expansión de volatilidad. |
| `regime_mean_reversion/` | Reversión a la media solo cuando el mercado está lateral. |

## Cómo agregar tu propia estrategia

1. Crea `strategies/mi_estrategia/` con `__init__.py`, `core.py` (señal y riesgo, sin llamadas a la API), `backtest.py` y `README.md`.
2. Usa `shared/backtest_engine.py` para cargar velas y simular, y `shared/config.py → client_from_env()` para conectarte a Bitget.
3. Antes de operar, pásala por `herramientas/walkforward.py` y compárala contra datos barajados.

← [3 · Datos y backtest](03-datos-y-backtest.md) · Siguiente: [5 · Despliegue →](05-despliegue.md)
