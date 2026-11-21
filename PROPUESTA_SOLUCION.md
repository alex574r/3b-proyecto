# Validat3B — Propuesta de solución

> Análisis hecho solo sobre los archivos locales. **No se llamó al endpoint de Foundry.**

## 1. Qué hay en la carpeta (y qué falta)

| Ruta | Contenido |
|---|---|
| `Validat3B_desarrollo_imagenes/imagenes/` | 300 JPG = 100 capturas × (`facade`, `product`, `shelf`). 47 KB – 1.7 MB (mediana 107 KB); la fachada puede ser 4096×3072 y el resto ~720×960 |
| `Validat3B_desarrollo_metadatos/capturas.csv/.json` | 100 filas con etiqueta (`decision_esperada`, `motivo_rechazo`) |
| `Validat3B_desarrollo_metadatos/catalogo_productos.csv` | 135 SKU (descripción, código de barras, rango de precio, unidad, línea) |
| `LEEME.md` | Diccionario de datos |
| los dos `.zip` | Copias de lo anterior |

**No vienen en la descarga** (están en la página del reto o se liberan después): documento de reglas de negocio, esquema JSON oficial, lista oficial de `reason_code`, script de costo operativo, notebook de arranque. Sin la lista de `reason_code` no se puede cerrar el mapeo de motivos (sección 5). Además **Python no está instalado** en esta máquina (solo el alias de la Microsoft Store); hay Node. Hay que instalar Python 3.11+ antes de empezar.

## 2. Hallazgos de los datos

1. **El set de desarrollo es 33 aprobadas / 34 rechazadas / 33 revisión manual**. Producción no se parece a esto (el 61 % de los rechazos reales es identidad de producto).
2. **Los rechazos del dev solo tienen 3 motivos**: capturas lejanas 18, borrosas 11, descripción incompleta 5. No hay ni un caso de "contratipo inválido", "producto no coincide", "fachada incorrecta" ni "sin etiqueta" en dev. El set ciego probablemente sí los trae, así que **no se puede afinar solo contra estos 100**.
3. **Los metadatos no discriminan nada**: en las 100 filas `capture_barcode == product_barcode` y el precio capturado está dentro de `[min,max]`. La señal está 100 % en las fotos.
4. **El precio capturado ≠ precio de referencia en 40 % de las filas** (también en 11 aprobadas), así que "precio distinto al catálogo" no es motivo de rechazo. Lo que sirve es comparar el precio capturado contra **el que dice la etiqueta**.
5. Cada captura tiene su propia fachada (100 únicas). Cadenas: Soriana 26, Bodega Aurrera 23, Bara 17, Neto 16, Walmart 12, Chedraui 6.

### Lo que se ve en las fotos (6 capturas revisadas a mano)

| Captura | Etiqueta | Qué pasa | Lección |
|---|---|---|---|
| CAP-645667 | aprobada | Producto nítido, etiqueta legible ($10.00), precio capturado = 10 | Caso limpio. Ojo: la etiqueta dice "Bayo" y el producto es "Negros" y aun así se aprobó → la regla de descripción es tolerante |
| CAP-305088 | rechazada, borrosa | La foto del producto es **una foto a una pantalla** (moiré, volteada) | "Borrosa" incluye foto-a-pantalla; se detecta con frecuencia espacial, no solo con nitidez |
| CAP-111555 | rechazada, lejana | La foto del producto es un anaquel completo, sin producto protagonista | Proporción del producto en el encuadre |
| CAP-757048 | rechazada, desc. incompleta | Anaquel de pastas variadas; la etiqueta dice "ESTRELLA", lo esperado es "moñito" | Hay que leer la etiqueta y compararla con la descripción esperada |
| CAP-350077 | revisión manual | Producto SOS 1 kg claro, etiqueta $30 pero movida/borrosa; el código bajo la etiqueta parece **no coincidir** con el capturado | Revisión manual = evidencia ambigua, no mala |

Lectura: **revisión manual es la clase "no puedo asegurarlo"**, y es donde el motor debe mandar todo lo dudoso.

## 3. Economía de la decisión (lo que manda el diseño)

Con la tabla de costos (manual 1, rechazar válida 3, aprobar inválida 10), sea `p` = probabilidad calibrada de que la captura sea válida:

| Acción | Costo esperado | Conviene si |
|---|---|---|
| Aprobar | 10·(1−p) | p > 0,90 |
| Rechazar | 3·p | p < 0,33 |
| Manual | 1 | 0,33 ≤ p ≤ 0,90 |

Además el filtro de entrada exige **precisión de aprobaciones ≥ 97 %**, así que en la práctica el umbral de aprobar sube a ~0,97 calibrado. Consecuencia: el motor es un **clasificador con tres zonas y umbrales asimétricos**, no un "¿es válida?" binario. Costo operativo = 50 % de la nota, así que todo el esfuerzo va a **calibrar `p`**, no a maximizar aciertos.

## 4. Arquitectura propuesta (un pase por captura, con escalamiento)

```
capture_id ─► [A] Chequeos locales (sin tokens)
               ├ metadatos: barcode capturado vs catálogo, precio vs rango, SKU existe
               ├ calidad por foto: varianza del Laplaciano (borrosa), FFT/moiré (pantalla), brillo
               ├ código de barras decodificado de la etiqueta (zxing-cpp / pyzbar) vs capturado
               └ OCR local de la etiqueta (RapidOCR/Tesseract): precio, descripción
          ─► [B] 1 llamada a claude-haiku-5-5 con las 3 fotos reducidas (~1024 px) + esperado
               Extracción estructurada, NO veredicto:
               cadena en fachada · marca/variante/gramaje visibles · producto protagonista (sí/no)
               · etiqueta legible · precio y tipo (regular/oferta/volumen) · foto de pantalla · distancia
          ─► [C] Motor de reglas + score p calibrado  →  aprobar / rechazar / manual
          ─► [D] Solo la zona gris (0,33–0,97): 2.º pase con recortes de la etiqueta y del producto en alta resolución
          ─► [E] Validación contra el esquema JSON; si falla → reintento; si sigue fallando → revision_manual válido
```

Por qué así:
- **Eficiencia (10 %)**: A es gratis; B es una sola llamada con imágenes reducidas; D solo para dudosos. Las fachadas de 4096×3072 se reducen siempre antes de enviar.
- **Auditabilidad**: cada `validaciones.*` y la `explicacion` salen de campos concretos (barcode leído, precio leído, nitidez), no de la opinión libre del modelo.
- **Seguridad del 97 %**: aprobar exige que **todas** las señales estén en verde a la vez (A y B coinciden). Si el OCR local y Haiku discrepan en precio o código → manual.
- **Calidad del dato (15 %)**: `precio_detectado` sale de OCR + Haiku por consenso; si no coinciden, se reporta el de la etiqueta y se baja la confianza. Detectar "oferta/por volumen/regular" viene gratis en la extracción de B (letreros "2 x $9", "GRATIS con 80 puntos", precio por gramo).

### Mapeo frente → señal (cubre las tres familias del reto)

| Frente | Señales | Fallo típico |
|---|---|---|
| A. Identidad (~61 %) | marca capturada vs marca visible, variante y gramaje, descripción de etiqueta vs `product_name`, contratipo permitido (catálogo), barcode de la etiqueta vs catálogo | `PRODUCTO_NO_COINCIDE`, contratipo, descripción incompleta |
| B. Evidencia (~29 %) | nitidez, moiré/pantalla, producto protagonista (lejanía), fachada coincide con cadena | borrosa, lejana, fachada incorrecta |
| C. Precio (~10 %) | etiqueta presente y legible, precio unitario, precio OCR vs capturado | sin etiqueta, sin precio |

El frente A pesa más, y es justo el que el dev **no ejercita**. Hay que fabricar casos de prueba (ver sección 6).

## 5. Calibración y reglas de decisión

- **Features** (≈15–20): nitidez por foto, flag de pantalla, `barcode_match`, `precio_ocr == capture_price`, `desc_match`, `producto_protagonista`, `etiqueta_legible`, `cadena_ok`, banderas de Haiku, nº de discrepancias OCR vs Haiku.
- **Modelo**: reglas duras primero (cualquier fallo claro de identidad → rechazar con su motivo; cualquier ambigüedad → manual), y encima una regresión logística pequeña con validación cruzada para producir `p`. Con 100 filas **no** usar nada más complejo.
- **`confidence_score`**: `p` para aprobar, `1−p` para rechazar, y para manual la confianza en "no se puede decidir".
- **`reason_code`**: prioridad determinista (identidad > evidencia > precio) usando la lista oficial. Pendiente de esa lista.
- **Principio de reserva**: ante cualquier duda → `revision_manual`. Nunca gana "todo a manual" (cuesta 1 por captura) pero aprobar mal cuesta 10×.

## 6. Plan en 6 h

| Tiempo | Entregable |
|---|---|
| 0:00–0:30 | Instalar Python, bajar reglas/esquema/`reason_code`/script de costo de la página del reto; cargar datos; replicar el script de costo contra las 100 etiquetas |
| 0:30–1:30 | Bloque A: nitidez, moiré, barcode, OCR; ver qué separa cada clase en dev |
| 1:30–3:00 | Bloque B: prompt de extracción JSON + llamada con las 3 fotos; medir tokens por captura (primer uso del endpoint) |
| 3:00–4:00 | Motor de reglas + `p` calibrado; búsqueda de umbrales con validación cruzada; medir costo y precisión de aprobaciones |
| 4:00–4:45 | **Set sintético para frente A**: tomar capturas buenas y cruzar la foto de producto/etiqueta con la de otra captura para simular "producto no coincide" y "sin etiqueta"; probar que el motor rechaza/manda a manual |
| 4:45–5:30 | Bloque D (zona gris), validación del esquema, reintentos, corrida completa y log de tokens |
| 5:30–6:00 | Ficha técnica de 1 página y guion de pitch de 3 min |

## 7. Riesgos y decisiones abiertas

1. **No se sabe si una captura con etiqueta `revision_manual` cuenta como 0 puntos cuando respondes manual.** La tabla oficial solo dice "enviada a revisión manual = 1". Si la verdad de las 33 manuales fuese "válida/inválida" real, el costo mínimo no es 0. Confirmar con el script de costo oficial antes de afinar umbrales.
2. **Sobreajuste**: 100 filas y solo 3 motivos de rechazo. Los umbrales se calibran para ser conservadores, no para maximizar acierto en dev.
3. **Llave de API**: venía pegada en el mensaje. Se usa solo por variable de entorno `FOUNDRY_API_KEY`; nunca en el código, notebook ni ficha técnica. Si el chat se comparte, conviene pedir rotación.
4. **Privacidad de imágenes**: OCR y visión clásica corren locales; solo se permite el endpoint asignado como IA externa.
5. **Límite de tokens/min compartido**: la corrida del set ciego debe poder reanudarse (guardar un JSON por captura a medida que sale) y respetar reintentos con espera.
6. **Haiku es el modelo disponible**: razona peor que modelos mayores, por eso el diseño le pide extracción y deja la decisión a reglas auditables.
