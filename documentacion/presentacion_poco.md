# Presentación con el POCO

El capturista puede seguir recorriendo la tienda mientras el servidor analiza las fotos. El auditor abre el mismo identificador en la web para comprobar qué evidencia respaldó la decisión.

## Orden para los tres minutos ante el jurado

| Tiempo | Qué mostrar | Qué decir |
|---|---|---|
| 0:00–0:25 | Las tres fotos originales del primer caso, en orden de fachada, producto y etiqueta. | «Necesitamos saber de qué tienda viene el precio, a qué presentación pertenece y cuánto marca la etiqueta». |
| 0:25–0:55 | **Comenzar captura** en el POCO. Elige las tres imágenes del mismo caso en la galería y pulsa **Guardar captura**. | «El capturista puede seguir con el siguiente producto mientras se analiza el anterior». |
| 0:55–1:25 | La etiqueta de anaquel en la muestra local. | «Si el recorte conserva el importe y la descripción, el selector puede ampliarlo y mejorar el contraste. Cuando hay dudas, conserva la foto completa. El modelo recibe una vista de la etiqueta por solicitud». |
| 1:25–2:10 | En **Historial**, lee el ID de la captura enviada. Abre ese mismo folio en el portal y muestra la etiqueta y el motivo del dictamen. | «Leer bien el precio resuelve una parte. Si la tienda no se puede confirmar, el caso llega al auditor». |
| 2:10–2:40 | Abre un caso rechazado en **No aprobadas** y alterna entre **Producto** y **Etiqueta**. | «Aquí el encuadre es lejano. El sistema deja el precio vacío y señala qué evidencia falló». |
| 2:40–3:00 | Vuelve al resumen del portal. | «Para 3B, el beneficio es que el equipo de campo sigue avanzando y el auditor puede comprobar cada decisión antes de usar ese precio». |

## Preparar las fotos originales para mostrar sin internet

El [generador de la muestra](preparar_muestra.py) lee los JPEG directamente del ZIP oficial y los incorpora a un HTML que puedes abrir con doble clic. Cada caso necesita el ID del dataset, un título y el JSON real de la API que corresponda a esas fotos. El JSON del portal USB se guarda en `%LOCALAPPDATA%\Validat3B\portal-usb\SERIE\json\APP-ID.json`. Verifica que la captura se hizo con las tres imágenes del ID elegido.

Desde la raíz del repositorio, sustituye los valores entre comillas por los de tu ensayo.

```powershell
python documentacion/preparar_muestra.py "ruta\Validat3B_desarrollo_imagenes.zip" --caso "ID_DATASET_1" "Primer producto" "ruta\primer_registro.json" --caso "ID_DATASET_2" "Segundo producto" "ruta\segundo_registro.json"
```

Abre `salida_presentacion/muestra.html` antes de la exposición. Las seis fotos y los dictámenes se ven sin red. El enlace de cada folio abre el portal de la laptop cuando está encendido.

## Antes de presentar

1. Mantén el POCO con internet y conectado a la laptop por USB. Abre la app instalada y deja el portal autenticado en una pestaña visible. Con una buena captura y una rechazada ya abiertas en otras pestañas puedes explicar los dos resultados aunque falle la red.
2. En la modalidad USB, abre `http://127.0.0.1:18124/portal/` en la laptop e introduce solo el valor de la credencial de auditoría. La app envía las fotos al dominio público. La laptop copia desde el historial del POCO los resultados enviados y sus tres fotos. Las resoluciones tomadas aquí quedan en esa laptop.
3. Si necesitas arrancar de nuevo el portal USB, usa el comando siguiente desde la raíz de `dev` en Windows. Requiere las dependencias del backend, la APK de depuración y un dispositivo autorizado en `adb devices`. La terminal debe permanecer abierta durante la presentación.

```powershell
$adbBin = Join-Path $env:LOCALAPPDATA 'Android\Sdk\platform-tools\adb.exe'
& $adbBin devices
python validat3b/portal_usb.py --adb "$adbBin" --serial <serie-del-POCO>
```

Sustituye `<serie-del-POCO>` por el identificador de la primera columna. En una terminal interactiva el programa pide la credencial de forma oculta si el entorno aún no tiene `VALIDAT3B_AUDIT_TOKEN` o `VALIDAT3B_TOKEN`. Si el portal ya abre y muestra capturas, puedes usar ese proceso.

## Recorrido en vivo

1. En **Comenzar captura**, reúne en orden la fachada, el producto y la etiqueta. Para una toma en vivo, encuadra el letrero de la tienda, la presentación del empaque y una etiqueta con el importe completo. Para repetir el caso ensayado, usa las tres fotos del mismo ejemplo desde la galería.
2. Deja vacíos los campos opcionales si quieres demostrar qué pudo leerse de las fotos. Pulsa **Guardar captura** una vez. Muestra que la app permite empezar la siguiente mientras procesa el envío.
3. Abre **Historial**. Cuando marque **Enviada**, abre el resultado y lee su `capture_id`. Este estado confirma que el servidor contestó. El dictamen puede ser aprobación, rechazo o revisión manual.
4. En la computadora abre **Revisión manual**, **No aprobadas** o **Aprobadas** según ese dictamen. Busca el ID y abre la ficha. Muestra la foto de producto, la etiqueta y la explicación. En un caso dudoso, el auditor puede registrar una resolución separada del dictamen original.

## Si algo tarda

- **Pendiente en el teléfono.** Comprueba internet y deja la captura en la cola. Si el historial muestra **Error**, abre el detalle antes de reintentar.
- **Enviada y aún no visible.** Comprueba el cable, que el equipo siga autorizado en `adb devices`, y el filtro de la bandeja. El puente revisa el teléfono cada cinco segundos y la pestaña visible consulta cada quince. Estos intervalos empiezan a importar una vez que el backend ya respondió.
- **Bandeja pública con 404.** Para publicar el portal compartido, el equipo del túnel debe ejecutar la versión integrada de `dev`. Para el ensayo por USB usa el puerto 18124.
