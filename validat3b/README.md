# Validat3B – motor de validación (esqueleto)

Flujo por captura: chequeos locales (nitidez, código de barras) → 1 llamada a Haiku (extracción estructurada)
→ reglas → JSON oficial. Ante cualquier error la captura sale como `revision_manual` con JSON válido.

## Requisitos
Python 3.10+ (en esta máquina aún no está instalado) y `pip install -r requirements.txt`.
La llave va **solo** en variable de entorno:

```powershell
$env:FOUNDRY_API_KEY = "<api-key>"
```

## Uso (desde esta carpeta)
```powershell
python tests/test_core.py                       # pruebas offline, sin red
python run.py --data ..\Validat3B_desarrollo_metadatos\capturas.json --images ..\Validat3B_desarrollo_imagenes --out salida --no-llm --limit 10
python run.py --data ..\Validat3B_desarrollo_metadatos\capturas.json --images ..\Validat3B_desarrollo_imagenes --out salida
python evaluate.py --data ..\Validat3B_desarrollo_metadatos\capturas.json --results salida\resultados.json
```
`--no-llm` no llama al endpoint. `--redecide` recalcula las decisiones con las respuestas de Haiku ya guardadas en `debug/` (para ajustar reglas sin gastar tokens). La corrida se reanuda: las capturas con `salida/<id>.json` se saltan.
Salidas: `salida/<id>.json` (oficial), `salida/resultados.json` (consolidado), `salida/debug/` (rasgos locales + respuesta de Haiku, para calibrar), `salida/usage.jsonl` (tokens).

## API para la app (`server.py`)
```powershell
$env:FOUNDRY_API_KEY = "<api-key>"          # solo vive en el servidor
$env:VALIDAT3B_TOKEN = "<token-fijo>"        # opcional: X-Api-Key (Bruno)
$env:VALIDAT3B_JWT_SECRET = "<secreto>"      # opcional: la app firma un JWT HS256 de 5 min con este secreto
python server.py                             # en producción: .\iniciar_publico.ps1 (lee .env)
python server.py --host 0.0.0.0              # celular físico en la misma red: http://<IP-del-PC>:8000
python server.py --no-llm                    # sin llamar a Foundry (solo chequeos locales)
python tests/test_server.py; python tests/test_auto.py   # pruebas de la API y del modo automático, sin red
```
`POST /validar` recibe los campos de `capturas.json` más `facade_b64`, `product_b64`, `shelf_b64` (JPEG en base64) y
`POST /analizar` solo necesita las 3 fotos. Los dos responden con un registro con la forma y el orden de `capturas.json`
(`capture_id` … `decision_esperada`, `motivo_rechazo`; las fotos se guardan en `salida_api/imagenes/` y se sirven en
`GET /imagenes/...`) seguido del detalle del motor (`precio_descuento`, `reason_code`, `explicacion`...). El archivo oficial del
set ciego lo sigue generando `run.py`. Contrato completo y errores en `API.md`.
La app Android está en `../3bApp` (pantalla `ValidarScreen`, cliente `ValidatApi.kt`).

## Estado actual
- **Aprobación automática desactivada** (`ALLOW_APPROVE = False` en `engine/decide.py`). En las 100 de dev,
  6 de 22 aprobaciones fueron malas; las candidatas salen como `revision_manual` con `CANDIDATA_APROBACION`.
  Reactivar cuando se confirme cómo puntúa el script oficial una captura con etiqueta `revision_manual`.
- **Rechazo por identidad desactivado** (`REJECT_IDENTITY = False`). En dev acertó 1 de 5 (Haiku es más estricto
  que 3B con gramaje y variante, y no hay lista de contratipos). Esas capturas van a `revision_manual`.
  Hoy solo se rechaza por calidad: foto a pantalla, borrosa (confirmada localmente), lejana y sin etiqueta.
- En dev la etiqueta está casi totalmente correlacionada con hora y tienda de captura (lotes). No se usa como
  señal: no es criterio de analista y probablemente no se repite en el set ciego.

## Analizar una carpeta (ventana)
```powershell
$env:FOUNDRY_API_KEY = "<api-key>"      # opcional: sin ella solo corren los chequeos locales
python gui.py
```
Elige una carpeta con fotos `<ID>_facade.jpg`, `<ID>_product.jpg` y `<ID>_shelf.jpg` (como `Validat3B_desarrollo_imagenes`; busca
también en subcarpetas) y pulsa **Analizar carpeta**. Con Haiku activo pide confirmación y avisa el costo estimado (~3.9k tokens por
captura). La tabla muestra decisión, motivo, tienda, producto, precio y oferta; doble clic (o **Ver JSON**) abre el registro completo.
Guarda un JSON por captura (el mismo registro que devuelve la API) y `resultados.json` en `salida_carpetas/<nombre de la carpeta>/`
dentro del proyecto. Al terminar, **Exportar JSON…** escribe un solo archivo con los datos de la corrida (carpeta, fecha, si usó Haiku),
un resumen (por decisión, por motivo y por tienda) y el registro completo de todas las capturas. Por defecto reutiliza los JSON ya
guardados para no gastar tokens dos veces. Lógica en `engine/carpeta.py`;
prueba sin red: `python tests/test_carpeta.py`.

La API también guarda cada registro que devuelve en `salida_api/json/<capture_id>.json` (y las fotos en `salida_api/imagenes/`).
Las carpetas `salida*/` las ignora git porque contienen datos de 3B.

## Rellenar nulos desde el catálogo
```powershell
python rellenar.py salida_api\json --dry-run     # solo cuenta lo que se rellenaría
python rellenar.py salida_api\json               # un archivo .json o una carpeta (registro, lista o exportación de la ventana)
python rellenar.py salida_carpetas --catalogo ..\Validat3B_evaluacion_metadatos\catalogo_productos.csv
```
Busca el producto por `id_product`, código de barras o, si no hay, nombre y contenido (solo coincidencias claras) y rellena
únicamente los campos que estén en `null`; nunca pisa un valor. Deja `fuente_catalogo` con el método usado. El mismo criterio
se aplica solo en los análisis nuevos (API, app y ventana). Con las 150 capturas de dev y ciego: por código o id acierta las 150;
solo por nombre y contenido acierta 142, se equivoca 0 y deja 8 sin rellenar. Catálogo por defecto: `VALIDAT3B_CATALOGO`, o el de
`Validat3B_evaluacion_metadatos`, o el de desarrollo. Lógica en `engine/catalogo.py`; prueba: `python tests/test_catalogo.py`.

## API pública (https://api.jamp.digital) — contrato completo en [API.md](API.md)
Túnel de Cloudflare `validat3b` → `http://127.0.0.1:8000` (config en `%USERPROFILE%\.cloudflared\config.yml`).
```powershell
$env:FOUNDRY_API_KEY = "<api-key>"
.\iniciar_publico.ps1          # -NoLlm para probar sin gastar tokens; Ctrl+C detiene API y túnel
```
La primera vez genera `validat3b\.env` con `VALIDAT3B_TOKEN` (ignorado por git). La API exige ese valor en el
header `X-Api-Key`; en la app va en el campo "Token". La PC debe estar encendida y el script corriendo.

## Provisional (reemplazar al bajar el material oficial)
- `engine/output.py`: lista de `reason_code`, valores de `validaciones` (`ok/falla/no_evaluable`) y esquema.
- `engine/decide.py`: umbrales (`BLUR_MIN`) y confianzas fijas; falta `DESCRIPCION_INCOMPLETA` y calibrar `p`.
- `evaluate.py`: réplica de la tabla de costos; supuesto sobre la etiqueta `revision_manual`.
- `engine/local_checks.py`: `moire_score` se registra pero la decisión aún no lo usa.
- El código de barras leído de las fotos no bloquea la aprobación: en dev solo 12/33 aprobadas tienen código legible y 6 de esas no coinciden con el capturado (se lee el de la caja u otro). Mejorar la lectura antes de usarlo como señal.
- `BLUR_MIN=40` casi nunca dispara: las medianas de nitidez son ~680 (aprobadas) vs ~160–230 (borrosas). Calibrar con `salida/debug/`.
- Falta OCR local de la etiqueta (hoy el precio sale solo de Haiku).
