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

## Provisional (reemplazar al bajar el material oficial)
- `engine/output.py`: lista de `reason_code`, valores de `validaciones` (`ok/falla/no_evaluable`) y esquema.
- `engine/decide.py`: umbrales (`BLUR_MIN`) y confianzas fijas; falta `DESCRIPCION_INCOMPLETA` y calibrar `p`.
- `evaluate.py`: réplica de la tabla de costos; supuesto sobre la etiqueta `revision_manual`.
- `engine/local_checks.py`: `moire_score` se registra pero la decisión aún no lo usa.
- El código de barras leído de las fotos no bloquea la aprobación: en dev solo 12/33 aprobadas tienen código legible y 6 de esas no coinciden con el capturado (se lee el de la caja u otro). Mejorar la lectura antes de usarlo como señal.
- `BLUR_MIN=40` casi nunca dispara: las medianas de nitidez son ~680 (aprobadas) vs ~160–230 (borrosas). Calibrar con `salida/debug/`.
- Falta OCR local de la etiqueta (hoy el precio sale solo de Haiku).
