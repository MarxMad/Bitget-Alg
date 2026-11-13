# Funding Rate Harvesting (Carry)

> **Hipótesis:** los perps pagan/cobran *funding* cada 8h. Si te posicionas en el
> lado que **cobra** el funding, ganas un flujo recurrente — un edge **no
> especulativo** (no dependes de adivinar la dirección).

## Señal / mecánica
- Leer el funding rate (endpoint público de Bitget de *current funding rate*).
- Si funding es muy positivo (longs pagan a shorts) → estar **corto** cobra funding.
- Si es muy negativo (shorts pagan a longs) → estar **largo** cobra funding.
- Idealmente **delta-neutral** (hedge del riesgo direccional). Con la cuenta unificada
  se puede cubrir con spot; sin hedge es una versión direccional con riesgo de precio.

## Enemigos
- El riesgo direccional puede superar al funding cobrado si no hay hedge.
- Funding puede cambiar de signo.

## Estado
⚪ Scaffolding. Requiere serie histórica de funding (endpoint o registro propio)
para backtestear el carry neto vs el movimiento de precio.
