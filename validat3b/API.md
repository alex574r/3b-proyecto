# API Validat3B

Base: `https://api.jamp.digital` (túnel de Cloudflare → `server.py` en el PC). Solo responde si el PC está
encendido y `iniciar_publico.ps1` corriendo.

## Autenticación
Todas las peticiones `POST` llevan una de estas dos credenciales (los valores están en `validat3b\.env`):
- `X-Api-Key: <VALIDAT3B_TOKEN>` (token fijo; lo usa Bruno), o
- `Authorization: Bearer <JWT>`: HS256 firmado con `VALIDAT3B_JWT_SECRET` y con `exp` a lo sumo 15 min adelante (se toleran 30 s de desfase
  de reloj; otro `alg` o un `exp` ausente/vencido se rechaza). La app Android genera uno nuevo en cada petición (`ValidatApi.jwt`).

Sin credencial válida: `401 {"error": "token inválido"}`. `GET /health` no pide nada.

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

## `POST /analizar`
Para la app: solo las 3 fotos (`facade_b64`, `product_b64`, `shelf_b64`) son obligatorias. Cualquier campo de la tabla de `/validar`
(incluido `capture_store_name`) es opcional y, si viene, manda sobre lo detectado. Mismos códigos de error que `/validar`.
La respuesta `200` es un envoltorio; `resultado` es el JSON oficial de arriba, sin cambios:
```json
{
  "resultado": { "...": "JSON oficial" },
  "datos_detectados": {
    "capture_store_name": "Neto", "capture_barcode": "7506233812418", "capture_price": 12.0,
    "capture_brand": "Best Choice", "product_name": "Vinagre blanco",
    "unit_quantity_product": 1100.0, "unit_product": "mililitro", "fuente_producto": "catalogo"
  }
}
```
- Cada dato sale de lo que Haiku lee en las fotos; `capture_barcode` y el nombre/contenido salen del catálogo de producto cuando el código
  está en él (`fuente_producto`: `usuario` | `catalogo` | `foto` | `null`). Si hay varios códigos en las fotos se prefiere el que está en el catálogo.
- Sin datos esperados, el motor evalúa lo que se ve en las propias fotos (calidad, producto vs. etiqueta, precio legible); no compara
  contra un producto esperado. Para eso usa `/validar` con los datos esperados.
- Si algo falla por dentro: `200` con `resultado` = `revision_manual` / `ERROR_PROCESAMIENTO` y `datos_detectados` = `{}`.
- Cuesta lo mismo que `/validar` (~3.9k tokens de entrada, ~0.25k de salida).

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
