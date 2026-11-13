# Bitget-Algoritmo-API

Bots de trading algorítmico para **Bitget** en Python: desde descargar datos y hacer un backtest honesto hasta desplegar un bot que opera solo.

Es el repo del **Taller de Trading Algorítmico de CriptoUNAM × Bitget**. Todo se practica en **modo demo** (fondos simulados): no necesitas depositar dinero.

> ⚠️ Material educativo, no asesoría financiera. La mayoría de las estrategias de este repo **no tienen ventaja** después de comisiones, y el repo lo documenta. Ese es justo el aprendizaje.

---

## Empieza aquí

| Paso | Guía | Cuándo |
|---|---|---|
| 0 | [Antes del taller](guias/00-antes-del-taller.md): cuenta, KYC, 2FA | **Una semana antes** |
| 1 | [Instalación](guias/01-instalacion.md): Python, repo, dependencias | Antes del taller |
| 2 | [Tu API key demo](guias/02-api-key-demo.md): crearla y probarla | Taller, min 10–30 |
| 3 | [Datos y backtest](guias/03-datos-y-backtest.md) | Taller, min 30–70 |
| 4 | [Catálogo de estrategias](guias/04-estrategias.md) | Taller y después |
| 5 | [Despliegue](guias/05-despliegue.md): papel → demo → contenedor | Taller, min 80–115 |
| 6 | [Seguridad, errores y FAQ](guias/06-seguridad-y-faq.md) | Cuando algo falle |

Índice completo: [`guias/`](guias/README.md).

## Inicio rápido

```bash
git clone https://github.com/MarxMad/Bitget-Alg.git Bitget-Algoritmo-API
cd Bitget-Algoritmo-API
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                       # llena tus llaves demo
python herramientas/check_conexion.py      # ¿funciona tu API key?
```

## Estructura

```
Bitget-Algoritmo-API/
├── guias/              ← guías paso a paso para asistentes (empieza aquí)
├── herramientas/       ← utilidades generales
│   ├── check_conexion.py     revisa tu API key (solo lectura)
│   ├── descargar_datos.py    baja velas históricas de Bitget a data/bitget/
│   ├── scan_edges.py         prueba familias de estrategias en muchos activos
│   ├── significance_check.py ¿el resultado se distingue del azar?
│   └── walkforward.py        validación walk-forward (entrenar → probar)
├── strategies/         ← una carpeta por estrategia (código + README + resultados)
├── shared/             ← cliente de Bitget, configuración y motor de backtest
├── deploy/             ← Docker, systemd y Vercel
├── api/  dashboard.html  vercel.json   ← panel y cron en Vercel (cross-sectional)
├── Dockerfile  docker-compose.yml      ← contenedor del market maker
└── .env.example        ← plantilla de variables (copia a .env)
```

`data/` y `.env` están en `.gitignore`: tus datos y tus llaves nunca se suben.

## Estrategias

| Estrategia | Estado | Carpeta |
|---|---|---|
| Cross-sectional momentum | ✅ Única que superó su prueba de azar | [`cross_sectional`](strategies/cross_sectional/) |
| Market maker por volatilidad | 🟡 Breakeven: genera volumen sin perder | [`mm_bitget`](strategies/mm_bitget/) |
| Trend-following (cruce de EMAs) | 🟡 Robusto en XLM, no en ETH | [`trend_following`](strategies/trend_following/) |
| Momentum multi-timeframe | ❌ Sin ventaja robusta | [`momentum_mtf`](strategies/momentum_mtf/) |
| Funding carry, pares ETH/BTC, breakout, reversión con régimen | 📝 Ideas sin implementar | [`strategies/`](strategies/) |

Detalle de cada una, con comandos y resultados: [guía 04](guias/04-estrategias.md).

## Licencia

MIT. Úsalo para aprender; si operas con dinero real, la responsabilidad es tuya.
