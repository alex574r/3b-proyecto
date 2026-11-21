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
$env:VALIDAT3B_TOKEN = "<token-de-la-app>"   # opcional: la app lo manda en X-Api-Key
python server.py                             # emulador Android: http://10.0.2.2:8000
python server.py --host 0.0.0.0              # celular físico: http://<IP-del-PC>:8000 (permitir el firewall)
python server.py --no-llm                    # sin llamar a Foundry (solo chequeos locales)
python tests/test_server.py                  # pruebas de la API, sin red
```
`POST /validar` recibe los campos de `capturas.json` más `facade_b64`, `product_b64`, `shelf_b64` (JPEG en base64) y
devuelve el JSON oficial. Entradas inválidas -> 400; errores internos -> JSON válido `revision_manual`. `GET /health`.
La app Android está en `C:\Users\alex5\AndroidStudioProjects\3bApp` (pantalla `ValidarScreen`, cliente `ValidatApi.kt`).

## Estado actual
- **Aprobación automática desactivada** (`ALLOW_APPROVE = False` en `engine/decide.py`). En las 100 de dev,
  6 de 22 aprobaciones fueron malas; las candidatas salen como `revision_manual` con `CANDIDATA_APROBACION`.
  Reactivar cuando se confirme cómo puntúa el script oficial una captura con etiqueta `revision_manual`.
- **Rechazo por identidad desactivado** (`REJECT_IDENTITY = False`). En dev acertó 1 de 5 (Haiku es más estricto
  que 3B con gramaje y variante, y no hay lista de contratipos). Esas capturas van a `revision_manual`.
  Hoy solo se rechaza por calidad: foto a pantalla, borrosa (confirmada localmente), lejana y sin etiqueta.
- En dev la etiqueta está casi totalmente correlacionada con hora y tienda de captura (lotes). No se usa como
  señal: no es criterio de analista y probablemente no se repite en el set ciego.

## Provisional (reemplazar al bajar el material oficial)
- `engine/output.py`: lista de `reason_code`, valores de `validaciones` (`ok/falla/no_evaluable`) y esquema.
- `engine/decide.py`: umbrales (`BLUR_MIN`) y confianzas fijas; falta `DESCRIPCION_INCOMPLETA` y calibrar `p`.
- `evaluate.py`: réplica de la tabla de costos; supuesto sobre la etiqueta `revision_manual`.
- `engine/local_checks.py`: `moire_score` se registra pero la decisión aún no lo usa.
- El código de barras leído de las fotos no bloquea la aprobación: en dev solo 12/33 aprobadas tienen código legible y 6 de esas no coinciden con el capturado (se lee el de la caja u otro). Mejorar la lectura antes de usarlo como señal.
- `BLUR_MIN=40` casi nunca dispara: las medianas de nitidez son ~680 (aprobadas) vs ~160–230 (borrosas). Calibrar con `salida/debug/`.
- Falta OCR local de la etiqueta (hoy el precio sale solo de Haiku).
