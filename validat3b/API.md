# API Validat3B

Base: `https://api.jamp.digital` (túnel de Cloudflare → `server.py` en el PC). Solo responde si el PC está
encendido y `iniciar_publico.ps1` corriendo.

## Autenticación
Todas las peticiones `POST` llevan el header `X-Api-Key: <VALIDAT3B_TOKEN>` (el valor está en `validat3b\.env`).
Sin él o con otro valor: `401 {"error": "token inválido"}`. `GET /health` no lo pide.

## `GET /health`
`200 {"status": "ok", "llm": true}`. `llm: false` significa que el servidor corre con `--no-llm` (todo sale a revisión manual).

## `POST /validar`
Una captura por petición. `Content-Type: application/json` y `Content-Length` obligatorios (no se acepta chunked).

| Campo | Tipo | Requerido | Uso |
|---|---|---|---|
| `facade_b64` | string | sí | Foto de la fachada, imagen (JPEG recomendado) en base64 estándar, sin saltos ni `data:` |
| `product_b64` | string | sí | Foto del producto |
| `shelf_b64` | string | sí | Foto de la etiqueta de precio |
| `capture_store_name` | string | sí | Cadena/tienda seleccionada; se compara contra la fachada |
| `capture_price` | número | no | Precio capturado; se compara contra el de la etiqueta |
| `capture_barcode` | string o número | no | Solo dígitos |
| `product_name` | string | no | Producto esperado (descripción) |
| `capture_brand` | string | no | Marca capturada |
| `unit_quantity_product`, `unit_product` | número, string | no | Contenido esperado, p. ej. `1000`, `"gramo"` |
| `capture_id` | string | no | `[A-Za-z0-9_-]`, máx. 64. Si falta se genera `APP-xxxxxxxx` |

Cuanta más información esperada se envíe (nombre, marca, contenido), mejor puede juzgar el motor. Cualquier otro campo se ignora.
El cuerpo no puede pasar de 40 MB (≈ 3 fotos de 10 MB en base64); la app comprime a JPEG q85.

### Respuesta `200`
Siempre el JSON oficial, incluso si algo falla por dentro (en ese caso `revision_manual` / `ERROR_PROCESAMIENTO`).
```json
{
  "capture_id": "PRUEBA-001",
  "decision": "revision_manual",
  "confidence_score": 0.5,
  "reason_code": "EVIDENCIA_AMBIGUA",
  "validaciones": {"tienda_fachada": "no_evaluable", "producto": "no_evaluable",
                   "codigo_barras": "no_evaluable", "evidencia_precio": "ok"},
  "precio_detectado": 10.0,
  "codigo_barras_detectado": null,
  "explicacion": "texto para el analista"
}
```
- `decision`: `aprobada` | `rechazada` | `revision_manual`. **Hoy el motor no aprueba** (`ALLOW_APPROVE = False`): las capturas
  que se verían bien salen `revision_manual` con `CANDIDATA_APROBACION`.
- `validaciones.*`: `ok` | `falla` | `no_evaluable`.
- `precio_detectado`: precio leído de la etiqueta, o `null`. `codigo_barras_detectado`: código leído de las fotos, o `null`.
- `reason_code` (lista provisional, no es la oficial): `APROBADA`, `PRODUCTO_NO_COINCIDE`, `FOTO_DE_PANTALLA`, `IMAGEN_BORROSA`,
  `CAPTURA_LEJANA`, `FACHADA_INCORRECTA`, `SIN_ETIQUETA_PRECIO`, `DESCRIPCION_INCOMPLETA`, `EVIDENCIA_AMBIGUA`,
  `CANDIDATA_APROBACION`, `SIN_ANALISIS_VISUAL`, `ERROR_PROCESAMIENTO`.

### Errores (el cuerpo siempre es `{"error": "..."}`)
| Código | Causa |
|---|---|
| 400 | JSON inválido, falta una foto o `capture_store_name`, base64 inválido, `capture_id` inválido, `capture_price`/`capture_barcode` no numéricos |
| 401 | Token faltante o incorrecto |
| 404 | Ruta distinta de `/health` y `/validar` |
| 411 | Falta `Content-Length` |
| 413 | Cuerpo vacío o mayor a 40 MB |

Un 4xx no gasta tokens y no se reintenta tal cual. Un 200 con `ERROR_PROCESAMIENTO` sí se puede reintentar.

## Reglas para el cliente
1. **Timeout de lectura ≥ 90 s.** Con Haiku tarda unos 2–10 s (más si hay cola); Cloudflare corta a los 100 s.
2. **Un `capture_id` único por captura.** El servidor no guarda ni deduplica: repetir la petición vuelve a gastar ~3.9k tokens.
3. **Concurrencia baja (2–4 peticiones a la vez).** Todas comparten el límite de tokens por minuto de la llave de Foundry.
4. **No mandar las fotos de 3B por aquí.** Pasan por la red de Cloudflare; las reglas del reto piden mantener esos datos dentro del equipo.
5. La llave de Foundry vive solo en el servidor; el cliente nunca la ve ni la necesita.

## Ejemplo (Python)
```python
import base64, requests
b64 = lambda p: base64.b64encode(open(p, "rb").read()).decode()
r = requests.post("https://api.jamp.digital/validar", timeout=120,
                  headers={"X-Api-Key": "<VALIDAT3B_TOKEN>"},
                  json={"capture_id": "MI-001", "capture_store_name": "Soriana", "capture_price": 14.0,
                        "product_name": "Arena para gato", "capture_brand": "Cat-tit",
                        "unit_quantity_product": 2000, "unit_product": "gramo",
                        "facade_b64": b64("fachada.jpg"), "product_b64": b64("producto.jpg"), "shelf_b64": b64("etiqueta.jpg")})
r.raise_for_status()
print(r.json()["decision"], r.json()["reason_code"])
```
Cliente Android de referencia: `3bApp/app/src/main/java/com/example/a3bapp/ValidatApi.kt`.
