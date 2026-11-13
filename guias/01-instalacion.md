# 1 · Instalación

Tiempo: unos 15 minutos.

## Requisitos

| | Versión | Cómo revisarla |
|---|---|---|
| Python | 3.10 o mayor (recomendado 3.12) | `python3 --version` |
| Git | cualquiera | `git --version` |
| Docker *(opcional)* | cualquiera | `docker --version` |

¿No los tienes?
- **macOS:** `brew install python git` (instala [Homebrew](https://brew.sh) primero).
- **Windows:** instala Python desde [python.org](https://www.python.org/downloads/) marcando **"Add Python to PATH"**, y Git desde [git-scm.com](https://git-scm.com). Usa la terminal **PowerShell**.
- **Linux:** `sudo apt install python3 python3-venv git`.

## Pasos

```bash
# 1. Descarga el repo
git clone https://github.com/MarxMad/Bitget-Alg.git Bitget-Algoritmo-API
cd Bitget-Algoritmo-API

# 2. Crea un entorno virtual (aísla las librerías de este proyecto)
python3 -m venv .venv

# 3. Actívalo
source .venv/bin/activate          # macOS / Linux
# .venv\Scripts\Activate.ps1       # Windows (PowerShell)

# 4. Instala las dependencias
pip install -r requirements.txt

# 5. Crea tu archivo de configuración
cp .env.example .env               # Windows: copy .env.example .env
```

Cuando el entorno está activo, tu terminal muestra `(.venv)` al inicio. **Actívalo cada vez que abras una terminal nueva.**

## Comprueba que funciona

```bash
python herramientas/check_conexion.py
```

Debes ver la sección **1. PÚBLICO** con ✅. La sección privada dirá "Saltado" porque aún no tienes llaves: eso es normal, lo resolvemos en la [guía 2](02-api-key-demo.md).

```
═══ 1. PÚBLICO: sin llaves ═══
  ✅ precio               último = 69084.5
  ✅ libro de órdenes     bid 69089.4 / ask 69089.5
  ✅ velas 1m             5 velas, cierre = 69084.5
  ✅ contrato             mín 5 USDT · apalancamiento máx 150x
```

## Problemas comunes

| Síntoma | Solución |
|---|---|
| `python3: command not found` | Python no está instalado o no está en el PATH. |
| `ModuleNotFoundError: No module named 'dotenv'` | Olvidaste activar el entorno (`source .venv/bin/activate`) o el paso 4. |
| Windows: "la ejecución de scripts está deshabilitada" | Corre una vez `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. |
| Error de SSL o de conexión | Revisa el wifi; algunas redes escolares bloquean APIs de exchanges. Prueba con datos del celular. |

← [0 · Antes del taller](00-antes-del-taller.md) · Siguiente: [2 · Tu API key demo →](02-api-key-demo.md)
