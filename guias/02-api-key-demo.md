# 2 · Tu API key demo

Tiempo: unos 10 minutos, si ya tienes KYC y 2FA ([guía 0](00-antes-del-taller.md)).

Una **API key** deja que tu código opere tu cuenta sin tu contraseña. Vamos a crear una **Demo API key**: solo funciona con fondos simulados, así que un error en tu código no te cuesta dinero.

## 1. Crea la key en Bitget

1. Entra a [bitget.com](https://www.bitget.com) desde la laptop.
2. Activa el **modo Demo** (interruptor Demo / Trading demo).
3. Ve a **Perfil → Gestión de API** ([bitget.com/account/newapi](https://www.bitget.com/account/newapi)).
4. Elige **Crear Demo API key** y el tipo **generada por el sistema** (system-generated, también llamada HMAC).
5. Llena el formulario:

| Campo | Qué poner |
|---|---|
| Nombre | `taller-criptounam` |
| Passphrase | Una contraseña nueva **que anotes**. Bitget no la puede recuperar. |
| Permisos | **Trading de la cuenta unificada: lectura y escritura**, y **gestión de la cuenta: lectura**. |
| Retiros | **Nunca** lo actives. |
| IP | Déjalo vacío durante el taller (tu IP cambia de red en red). |

6. Confirma con tu código de 2FA, correo o SMS.
7. Bitget te muestra tres datos: **API key**, **Secret key** y tu **Passphrase**. El Secret **solo se muestra una vez**: cópialo ahora.

## 2. Pon las llaves en tu `.env`

Abre el archivo `.env` (lo creaste en la guía 1) con cualquier editor y llénalo:

```bash
BITGET_DEMO=1
BITGET_API_KEY=bg_xxxxxxxxxxxxxxxxxxxx
BITGET_SECRET_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
BITGET_PASSPHRASE=la-que-elegiste
```

- Sin comillas y sin espacios alrededor del `=`.
- `BITGET_DEMO=1` es obligatorio con una Demo API key: hace que cada petición lleve el encabezado `paptrading: 1`, que la dirige al entorno demo.
- `.env` está en `.gitignore`: **nunca** lo subas a GitHub ni lo compartas por chat.

## 3. Prueba la conexión

```bash
python herramientas/check_conexion.py
```

Resultado esperado:

```
Entorno: DEMO (fondos simulados)   ·   símbolo de prueba: BTCUSDT
...
═══ 2. PRIVADO: con tu .env ═══
  Firma: HMAC
  ✅ posiciones           0 abiertas
  ✅ órdenes pendientes   0 pendientes
  ✅ saldo                equity = 50000 USDT     ← tu saldo demo puede ser otro

  🎉 Tu API key funciona. Ya puedes seguir con la guía 03.
```

Si algo sale en ❌, debajo aparece una flecha `→` con lo que significa ese código de error. La lista completa está en la [guía 6](06-seguridad-y-faq.md#errores-de-bitget).

## Cómo funciona por dentro (opcional)

Cada petición privada va firmada. El código en `shared/bitget_client.py` hace esto:

```python
prehash = timestamp + "GET" + "/api/v3/account/assets" + body
firma   = base64( HMAC_SHA256(secret_key, prehash) )
```

Y manda la firma en los encabezados `ACCESS-KEY`, `ACCESS-SIGN`, `ACCESS-TIMESTAMP` y `ACCESS-PASSPHRASE`. Así Bitget sabe que la petición es tuya y que nadie la alteró en el camino, sin que tu secret viaje por internet.

← [1 · Instalación](01-instalacion.md) · Siguiente: [3 · Datos y backtest →](03-datos-y-backtest.md)
