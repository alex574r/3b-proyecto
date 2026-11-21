"""Una llamada a Haiku por captura: extracción estructurada de las 3 fotos (NO da veredicto)."""
import base64
import io
import json
import os
import threading
from pathlib import Path

from PIL import Image, ImageOps

ENDPOINT = "https://softwaredevelopment-resource.services.ai.azure.com/anthropic"
MODEL = "claude-haiku-5-5"
MAX_SIDE = 1024  # reducir siempre: la fachada original es 4096x3072

SYSTEM = (
    "Eres un auditor estricto de capturas de precios en tiendas de México. Tu trabajo es encontrar razones "
    "para NO aceptar una captura. Aprobar una captura mala cuesta 10 veces más que mandarla a revisión, "
    "así que ante cualquier duda responde \"dudoso\". Describe solo lo que se ve; no adivines. "
    "Responde únicamente con un objeto JSON válido, sin texto extra."
)

PROMPT = """Captura {capture_id}. Datos esperados:
- Cadena/tienda seleccionada: {store}
- Producto esperado: {name} | marca: {brand} | contenido: {qty} {unit}
- Precio capturado por el usuario: {price}

Fotos, en orden: 1) fachada de la tienda, 2) producto, 3) etiqueta de precio en anaquel.

Evalúa cada criterio con "ok", "falla" o "dudoso":
- fachada: la fachada muestra claramente la cadena seleccionada. "falla" si es otra cadena.
- pantalla: "falla" si la foto de producto o de etiqueta parece tomada a la pantalla de otro celular
  (moiré, píxeles, marco de teléfono, reflejos de vidrio, imagen volteada).
- nitidez: producto y etiqueta enfocados, sin movimiento. "falla" si están borrosos o movidos.
- cercania: el producto esperado es el protagonista de la foto 2. "falla" si es un anaquel completo
  o una toma lejana donde el producto no se distingue.
- producto: marca, variante/sabor y contenido visibles en la foto 2 coinciden con el esperado.
- etiqueta: la descripción de la etiqueta corresponde a ese mismo producto (marca, variante y contenido).
  "falla" si describe otra variante u otro producto; "dudoso" si está incompleta o no se lee.
- precio: hay etiqueta de precio y el precio se lee con claridad.

Devuelve este JSON:
{{
 "criterios": {{"fachada": "...", "pantalla": "...", "nitidez": "...", "cercania": "...",
               "producto": "...", "etiqueta": "...", "precio": "..."}},
 "cadena_visible": str|null,
 "descripcion_etiqueta": str|null,
 "precio_etiqueta": number|null,
 "tipo_precio": "regular"|"oferta"|"volumen"|"desconocido",
 "motivo": "una frase con el problema principal, o vacío si no hay"
}}"""

_log_lock = threading.Lock()


def _img_block(path):
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    im.thumbnail((MAX_SIDE, MAX_SIDE))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    data = base64.b64encode(buf.getvalue()).decode()
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}}


def make_client():
    from anthropic import AnthropicFoundry
    return AnthropicFoundry(api_key=os.environ["FOUNDRY_API_KEY"], base_url=ENDPOINT, max_retries=5)


def _parse_json(text):
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b < a:
        raise ValueError("la respuesta no contiene JSON")
    return json.loads(text[a:b + 1])


def extract(cap, paths, client, usage_log):
    content = [{"type": "text", "text": PROMPT.format(
        capture_id=cap["capture_id"], store=cap.get("capture_store_name"), name=cap.get("product_name"),
        brand=cap.get("capture_brand"), qty=cap.get("unit_quantity_product"), unit=cap.get("unit_product"),
        price=cap.get("capture_price"))}]
    for k in ("facade", "product", "shelf"):
        content.append(_img_block(paths[k]))
    msg = client.messages.create(model=MODEL, max_tokens=700, thinking={"type": "disabled"}, system=SYSTEM,
                                 messages=[{"role": "user", "content": content}])
    with _log_lock, open(usage_log, "a", encoding="utf-8") as f:
        f.write(json.dumps({"capture_id": cap["capture_id"], "input_tokens": msg.usage.input_tokens,
                            "output_tokens": msg.usage.output_tokens}) + "\n")
    text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
    try:
        return _parse_json(text)
    except ValueError as e:  # incluye el inicio de la respuesta para depurar
        kinds = [getattr(b, "type", "?") for b in msg.content]
        raise ValueError(f"{e}; stop={msg.stop_reason}; bloques={kinds}; texto={text[:300]!r}") from e
