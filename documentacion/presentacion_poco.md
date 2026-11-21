# Presentación con el POCO

El capturista puede seguir recorriendo la tienda mientras el servidor analiza las fotos. El auditor abre el mismo identificador en la web para comprobar qué evidencia respaldó la decisión.

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
