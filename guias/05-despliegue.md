# 5 · Despliegue

Tiempo: unos 20 minutos. Requiere tu `.env` con la Demo API key ([guía 2](02-api-key-demo.md)).

Desplegar es pasar de "funciona en mi backtest" a "corre solo, con límites, y sé qué está haciendo". Se hace en tres escalones, y no se salta ninguno:

```
 1. PAPEL            2. DEMO                     3. REAL
 simula órdenes      órdenes reales en el        dinero real
 en tu laptop        entorno demo de Bitget      (fuera del taller)
 sin --live          BITGET_DEMO=1  + --live     BITGET_DEMO=0 + --live
```

## 1. Preflight: revisa antes de operar

```bash
python strategies/mm_bitget/preflight.py
```

Revisa credenciales, firma, saldo y si la cuenta puede colocar órdenes. Para eso coloca una orden *post-only* muy lejos del precio (no se puede llenar) y la cancela de inmediato.

```
  ✅ credenciales en .env         completas · firma HMAC · DEMO
  ✅ API pública                  XLM a 0.2841
  ✅ autenticación                firma HMAC válida
  ✅ balance                      equity $50000.00
  ✅ permiso de trading           la cuenta puede colocar órdenes
```

## 2. Escalón 1: papel

Sin `--live`, el bot lee precios reales pero **simula** las órdenes en tu computadora:

```bash
python -m strategies.mm_bitget.strategy --once      # un ciclo y termina
python -m strategies.mm_bitget.strategy             # sigue corriendo (Ctrl+C para parar)
```

Mientras corre, abre [localhost:8080/status](http://localhost:8080/status) para ver su estado: cotizaciones, inventario, P&L y errores.

## 3. Escalón 2: demo

Con `BITGET_DEMO=1` en tu `.env`, `--live` manda órdenes **de verdad** al entorno demo de Bitget. Las ves aparecer en la app, en modo Demo.

```bash
python -m strategies.mm_bitget.strategy --live --symbols BTCUSDT
```

Déjalo correr unos minutos, revisa en la app tus órdenes abiertas y detenlo con **Ctrl+C**.

## Los frenos del bot

Un bot sin frenos es la forma más rápida de perder una cuenta. El market maker trae estos, en `strategies/mm_bitget/core.py`:

| Freno | Qué hace | Valor por defecto |
|---|---|---|
| Pérdida diaria máxima | Si pierde ese % del saldo en el día, cancela todo y se detiene. | 10 % |
| Inventario máximo | Deja de cotizar el lado que haría crecer una posición ya grande. | 10 órdenes |
| Apalancamiento total | Tope a la exposición total. | 5x |
| Tamaño por riesgo | Ajusta el tamaño de las órdenes a tu saldo en cada ciclo, para que la variación diaria esperada no pase de ese % del saldo. | 3 % |
| Solo *post-only* | Nunca toma liquidez ni puede cruzarse con sus propias órdenes. | siempre |

**Kill-switch manual:** Ctrl+C detiene el bot. Para cerrar todo de inmediato, cancela las órdenes y cierra posiciones desde la app.

## 4. En un contenedor (Docker)

Así corre en un servidor 24/7. El contenedor arranca en papel por defecto.

```bash
docker compose up --build -d                       # construye y arranca
docker compose logs -f market-maker                # ver logs
curl -s localhost:8080/status | python3 -m json.tool
docker compose down                                # detener
```

Para pasar a demo o real se edita `MM_ARGS` en `docker-compose.yml` (`"--live"`), nunca el código. Más detalle, incluido cómo rentar un servidor: [`deploy/DOCKER.md`](../deploy/DOCKER.md).

## 5. Estrategias diarias: GitHub Actions o Vercel

El cross-sectional momentum rebalancea una vez al día, así que no necesita un servidor encendido:

- **GitHub Actions:** `.github/workflows/rebalance.yml` lo corre cada día a las 07:10 UTC.
- **Vercel:** `api/rebalance.py` como cron y `dashboard.html` como panel. Ver [`deploy/VERCEL.md`](../deploy/VERCEL.md).

Las llaves van en los *secrets* de GitHub o en las variables de entorno de Vercel, nunca en el código.

## Para seguir practicando

Deja tu bot corriendo en **demo** unos días y revisa cada tanto [localhost:8080/status](http://localhost:8080/status): cuánto volumen hizo, cuánto ganó o perdió y si se activó algún freno. Es la mejor forma de entender cómo se comporta antes de pensar en dinero real.

← [4 · Catálogo de estrategias](04-estrategias.md) · Siguiente: [6 · Seguridad, errores y FAQ →](06-seguridad-y-faq.md)
