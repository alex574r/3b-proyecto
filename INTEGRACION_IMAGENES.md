# Integrar la cámara guiada y la preparación de etiquetas

La rama `integracion/validat3b` reúne el backend de `main`, el selector de `Leonardo` y la interfaz Android de `feat/figma-validat3b` de Balam. Android ayuda a encuadrar y guarda la captura para que la persona siga su recorrido. El servidor elige la vista de la etiqueta que recibirá el modelo. La app y el backend siguen usando el contrato HTTP existente.

## Integración en la rama del equipo

1. Revisar el cambio conjunto contra `main`. Desplegar el backend y generar la APK desde el mismo commit de integración. El portal `audit-demo/` consulta los registros de ese mismo servidor. La demostración de Balam se abre en `?modo=demo`. La app Android usa `POST /analizar` para capturas reales.
2. En el backend, instalar las dependencias de `validat3b/requirements.txt` en el entorno habitual. Desplegar juntos `validat3b/engine/etiqueta.py` y `vision.py` y reiniciar el servicio. La configuración de Foundry sigue en el servidor. Para las opciones de arranque y catálogo, consultar [el README del motor](validat3b/README.md).
3. En Android, sincronizar Gradle desde `3bApp/`, conservar la configuración local de URL y autenticación del entorno, y ejecutar `.\gradlew.bat assembleDebug` en Windows. El APK de prueba queda en `app/build/outputs/apk/debug/app-debug.apk`.
4. Probar en un celular del equipo antes de distribuir el APK. Para revertir, volver a desplegar la versión anterior del componente afectado. La mejora no introduce columnas nuevas en Room ni cambios en el esquema del JSON.

## Qué pasa al tomar una foto

En **Tomar foto**, la pantalla de cámara en `FuentesFoto.kt` solicita permiso de cámara y muestra la vista previa con una plantilla fija para fachada, producto o etiqueta. La indicación de acercarse busca que quepan juntos el importe y la descripción. «Mantén el teléfono quieto» permanece visible antes del disparo. La plantilla es una guía visual y la app conserva la opción de galería.

Al pulsar **Guardar captura**, `Repo.kt` guarda fotos y metadatos localmente y programa el envío mediante WorkManager. Al terminar el guardado local la app vuelve al inicio con la confirmación. **Comenzar captura** inicia otro registro mientras WorkManager envía el anterior. Antes de guardar, las tres miniaturas permiten reemplazar una foto. El historial conserva el estado y recibe la respuesta cuando termina el procesamiento. Una captura pendiente puede esperar a que vuelva la red aunque el usuario salga de la pantalla.

## Qué hace el backend

Durante la preparación de la consulta visual, `vision.py` aplica el selector únicamente a la foto de anaquel. `etiqueta.py` busca una región que incluya el importe completo y la descripción. Elige la foto completa ante ambigüedad o riesgo de cortar dígitos, un recorte cuando el encuadre es fiable o ese recorte con contraste local cuando corresponde. La elección ocurre antes de la llamada habitual a Foundry. Los chequeos locales siguen disponiendo de las fotos originales.

El registro de consumo añade `vista_etiqueta` (A completa, B recorte, C recorte con contraste), `motivo_vista` y `preparacion_etiqueta_ms`. El tiempo comprende abrir la imagen, seleccionar la vista y preparar el JPEG. En una medición local con 100 imágenes, la mediana fue 37 ms y el percentil 95 fue 178 ms. La red, la cola y la inferencia se miden por separado. El registro de consumo se escribe al recibir una respuesta del modelo.

## Comprobación de la integración

- Tomar las tres fotos. En la etiqueta deben caber el precio y la descripción dentro del marco. Probar también la galería si se deniega el permiso.
- Guardar una captura sin red y comenzar otra. Restablecer la red y verificar en el historial que aparecen el estado final y los campos devueltos por el servidor.
- En un entorno con Foundry configurado, procesar una captura y verificar en el registro la vista elegida y los milisegundos. La ejecución con `--no-llm` omite la preparación de la consulta visual.
- Para verificar la calidad de lectura, comparar el precio y el producto que lee Foundry con una referencia revisada. El piloto comprobó visualmente el encuadre. La precisión final de lectura y el costo real de inferencia siguen pendientes.

## Conectar Android, API y portal

1. **Backend**. En el servidor que ya recibe el tráfico de `https://api.jamp.digital`, desplegar esta revisión completa de `validat3b/` y reiniciar el proceso de la API con el mismo directorio persistente `validat3b/salida_api/`. Conservar los JSON, fotos, base de auditoría y configuración del equipo al actualizar. La cuenta del servicio necesita poder escribir en ese directorio. Una comprobación de despliegue es consultar `GET /auditoria/capturas` sin token: 401 indica que la ruta está instalada y protegida; 404 indica que todavía no se sirve esa ruta; 503 indica que falta configurar la credencial.
2. **Accesos**. La app usa el JWT temporal de la demo. Configurar `validat3b.jwtSecret` en `3bApp/local.properties` (ignorado por Git) y recompilar la APK. La web usa otro mecanismo: introduce `VALIDAT3B_AUDIT_TOKEN` en el formulario del navegador. Si no se configuró una clave específica, el backend acepta el token fijo del equipo `VALIDAT3B_TOKEN` para auditoría. No introducir el secreto de firma JWT en el portal. La credencial web vive en memoria y se pierde al recargar. Distribuir la APK de demostración solo al equipo y rotar las credenciales temporales al cerrar la prueba.
3. **Web**. Desde el repositorio en Linux, ejecutar `python3 -m http.server 8123 --bind 127.0.0.1 --directory audit-demo` y visitar `http://127.0.0.1:8123/`. El servidor estático solo entrega la interfaz; el navegador consulta la API por HTTPS. Por defecto la API admite los orígenes exactos `http://127.0.0.1:8123` y `http://localhost:8123`. Para otro alojamiento, configurar `VALIDAT3B_AUDIT_ORIGINS` con los orígenes permitidos separados por comas antes de iniciar la API. El proxy del dominio debe permitir OPTIONS, GET, POST y el encabezado X-Audit-Token. Para una prueba local aislada se admite `?api=http://127.0.0.1:8000`. La APK de campo siempre debe apuntar al dominio del equipo.
4. **Comprobación**. En el POCO guardar una captura y anotar el identificador que aparece en el historial. Buscar ese ID en la bandeja web y contrastar precio, producto, motivo y fotos. Si requiere revisión manual, registrar una resolución de prueba autorizada y confirmar que se conserva al reconectar. La auditoría web es posterior al dictamen del motor: el JSON original y el historial Android conservan el veredicto automático.
