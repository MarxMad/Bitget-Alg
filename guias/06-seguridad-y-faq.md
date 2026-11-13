# 6 · Seguridad, errores y FAQ

## Reglas de seguridad

1. **Nunca actives el permiso de retiro** en una API key de un bot.
2. **El `.env` no se comparte:** ni en GitHub, ni en Discord, ni en una captura de pantalla. Ya está en `.gitignore`; no lo saques de ahí.
3. **Si una llave se filtra, bórrala** en Bitget → Gestión de API y crea otra. Es más rápido que averiguar quién la vio.
4. **Una key por bot.** Si algo sale mal, revocas solo esa.
5. **En producción, ata la key a la IP** de tu servidor.
6. **Demo primero, siempre.** Un bot nuevo pasa al menos una semana en demo antes de tocar dinero real.

## Errores de Bitget

`herramientas/check_conexion.py` explica estos códigos automáticamente.

| Código | Significa | Qué hacer |
|---|---|---|
| `40006` | API key inválida o de otro entorno | ¿Demo API key sin `BITGET_DEMO=1`? ¿O key real con `BITGET_DEMO=1`? |
| `40009` | Firma inválida | Revisa `BITGET_SECRET_KEY`: sin espacios, sin comillas, completo. Revisa la hora de tu computadora. |
| `40011` / `40012` | Passphrase o key incorrecta | La passphrase no se recupera: borra la key y crea otra. |
| `40014` | Falta un permiso | Crea la key con permiso de trading (lectura y escritura). |
| `40035` | KYC pendiente | Completa la verificación de identidad. Ninguna orden se acepta sin ella. |
| `40037` | La key no existe | La copiaste incompleta o la borraste. |
| `40085` | Cuenta en modo clásico | Este repo usa la API v3: cambia tu cuenta a Cuenta Unificada (UTA). |

## Preguntas frecuentes

**¿Necesito poner dinero?**
No. El modo demo trae saldo simulado.

**¿Puedo usar la misma key en demo y en real?**
No. La Demo API key solo funciona con `BITGET_DEMO=1`, y una key real solo con `BITGET_DEMO=0`.

**`check_conexion` dice que el símbolo no existe en demo.**
Prueba otro símbolo con `BITGET_TEST_SYMBOL=ETHUSDT`. Si sigue fallando, avisa a un mentor: algunos pares tienen un nombre distinto en el entorno demo.

**El error dice que la firma o el timestamp son inválidos y mis llaves están bien.**
La hora de tu computadora está desfasada. Activa la hora automática en la configuración del sistema.

**¿Por qué el repo dice que casi nada funciona?**
Porque es cierto, y saberlo te ahorra dinero. Encontrar una estrategia que gane en un backtest es fácil; encontrar una que siga ganando con comisiones, en otro periodo y contra datos barajados, es difícil. La [guía 3](03-datos-y-backtest.md) explica cómo distinguirlas.

**¿Dónde pido ayuda después del taller?**
En la comunidad de CriptoUNAM: [criptounam.xyz](https://criptounam.xyz) · [@Cripto_UNAM](https://x.com/Cripto_UNAM).

← [5 · Despliegue](05-despliegue.md) · [Índice de guías](README.md)
