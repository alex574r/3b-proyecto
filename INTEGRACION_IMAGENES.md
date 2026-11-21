# Integrar la cámara guiada y la preparación de etiquetas

La rama `Leonardo` incluye dos cambios que se pueden desplegar por separado. Android ayuda a encuadrar y guarda la captura para que la persona siga su recorrido. El servidor elige la vista de la etiqueta que recibirá el modelo. La app y el backend siguen usando el contrato HTTP existente.

## Integración en la rama del equipo

1. Actualizar la rama de destino y abrir un pull request desde `Leonardo`. Al preparar la entrega, GitHub solo tenía `main`. La base usada fue `bdc8d1f`, que incluye precio de oferta, motivo de rechazo y datos del SKU en el historial.
2. En el backend, instalar las dependencias de `validat3b/requirements.txt` en el entorno habitual. Desplegar juntos `validat3b/engine/etiqueta.py` y `vision.py` y reiniciar el servicio. La configuración de Foundry sigue en el servidor. Para las opciones de arranque y catálogo, consultar [el README del motor](validat3b/README.md).
3. En Android, sincronizar Gradle desde `3bApp/`, conservar la configuración local de URL y autenticación del entorno, y ejecutar `.\gradlew.bat assembleDebug` en Windows. El APK de prueba queda en `app/build/outputs/apk/debug/app-debug.apk`.
4. Probar en un celular del equipo antes de distribuir el APK. Para revertir, volver a desplegar la versión anterior del componente afectado. La mejora no introduce columnas nuevas en Room ni cambios en el esquema del JSON.

## Qué pasa al tomar una foto

En **Tomar foto**, `CamaraGuiada.kt` solicita permiso de cámara y muestra la vista previa con una plantilla fija para fachada, producto o etiqueta. La indicación de acercarse busca que quepan juntos el importe y la descripción. «Mantén el teléfono quieto» permanece visible antes del disparo. La plantilla es una guía visual y la app conserva la opción de galería.

Al pulsar **Guardar captura**, `Repo.kt` guarda fotos y metadatos localmente y programa el envío mediante WorkManager. El formulario queda disponible después del guardado local. El historial conserva el estado y recibe la respuesta cuando termina el procesamiento. Una captura pendiente puede esperar a que vuelva la red aunque el usuario salga de la pantalla.

## Qué hace el backend

Durante la preparación de la consulta visual, `vision.py` aplica el selector únicamente a la foto de anaquel. `etiqueta.py` busca una región que incluya el importe completo y la descripción. Elige la foto completa ante ambigüedad o riesgo de cortar dígitos, un recorte cuando el encuadre es fiable o ese recorte con contraste local cuando corresponde. La elección ocurre antes de la llamada habitual a Foundry. Los chequeos locales siguen disponiendo de las fotos originales.

El registro de consumo añade `vista_etiqueta` (A completa, B recorte, C recorte con contraste), `motivo_vista` y `preparacion_etiqueta_ms`. El tiempo comprende abrir la imagen, seleccionar la vista y preparar el JPEG. En una medición local con 100 imágenes, la mediana fue 37 ms y el percentil 95 fue 178 ms. La red, la cola y la inferencia se miden por separado. El registro de consumo se escribe al recibir una respuesta del modelo.

## Comprobación de la integración

- Tomar las tres fotos. En la etiqueta deben caber el precio y la descripción dentro del marco. Probar también la galería si se deniega el permiso.
- Guardar una captura sin red y comenzar otra. Restablecer la red y verificar en el historial que aparecen el estado final y los campos devueltos por el servidor.
- En un entorno con Foundry configurado, procesar una captura y verificar en el registro la vista elegida y los milisegundos. La ejecución con `--no-llm` omite la preparación de la consulta visual.
- Para verificar la calidad de lectura, comparar el precio y el producto que lee Foundry con una referencia revisada. El piloto comprobó visualmente el encuadre. La precisión final de lectura y el costo real de inferencia siguen pendientes.
