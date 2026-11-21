# 3b-proyecto

[Guía de integración de la cámara, la cola y el selector de etiquetas](INTEGRACION_IMAGENES.md)

Motor de validación de capturas de precio (reto Validat3B).

- [validat3b/](validat3b/): código del motor, instrucciones de uso en su README.
- [3bApp/](3bApp/): app Android (Compose): tomas o eliges las 3 fotos, las envía a la API (`https://api.jamp.digital`, `POST /analizar`), llena sola los datos de la captura y muestra la decisión y el JSON. Cada análisis se guarda primero en Room (con sus fotos) y aparece en la pestaña Historial; si no hay red, hay timeout o el servidor falla (5xx), queda *pendiente* y WorkManager lo reenvía solo cuando vuelve la conexión (los errores 4xx pasan a *error* y se reintentan a mano). Abrir en Android Studio. En `3bApp/local.properties` (ignorado por git) define `validat3b.jwtSecret=<VALIDAT3B_JWT_SECRET de validat3b/.env>` y, opcional, `validat3b.apiUrl=<otra URL>`. La APK usa la URL compilada incluso si en el teléfono quedó una preferencia de depuración anterior.
- [PROPUESTA_SOLUCION.md](PROPUESTA_SOLUCION.md): análisis de los datos y diseño de la solución.

Los datos del reto (`Validat3B_desarrollo_*`) no se incluyen en el repositorio; colócalos en esta carpeta para ejecutar.

## Interfaz de Validat3B

La app Android usa cámara y galería integradas. El selector de Android también está disponible para elegir una imagen sin conceder acceso a la galería. Desde **Casos de demostración** se pueden abrir los siete resultados de ejemplo y simular un error de precio o de red. Las capturas reales y sus reintentos siguen disponibles en **Historial**.

Para compilar y ejecutar las pruebas unitarias con Android SDK 36:

```bash
cd 3bApp
bash gradlew :app:assembleDebug :app:testDebugUnitTest
```

Para abrir el portal web de auditoría en el navegador, inicia este servidor desde la raíz del repositorio y abre [el portal local](http://127.0.0.1:8123/):

```bash
python3 -m http.server 8123 --bind 127.0.0.1 --directory audit-demo
```

La portada conecta con `https://api.jamp.digital`. Introduce el token de auditoría que configure el operador. Las capturas recibidas en `POST /analizar` aparecen en el portal al actualizar la bandeja (también se refresca cada 15 segundos con la pestaña visible). Al abrir una captura se consultan sus fotos originales. Las resoluciones del auditor se guardan en la API. **Ver demo** abre por separado los ejemplos de Balam. [Configuración de la API y prueba de campo](INTEGRACION_IMAGENES.md).
