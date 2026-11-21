# 3b-proyecto

Motor de validación de capturas de precio (reto Validat3B).

- [validat3b/](validat3b/): código del motor, instrucciones de uso en su README.
- [3bApp/](3bApp/): app Android (Compose): tomas o eliges las 3 fotos, las envía a la API (`https://api.jamp.digital`, `POST /analizar`), llena sola los datos de la captura y muestra la decisión y el JSON. Cada análisis se guarda primero en Room (con sus fotos) y aparece en la pestaña Historial; si no hay red, hay timeout o el servidor falla (5xx), queda *pendiente* y WorkManager lo reenvía solo cuando vuelve la conexión (los errores 4xx pasan a *error* y se reintentan a mano). Abrir en Android Studio. En `3bApp/local.properties` (ignorado por git) define `validat3b.jwtSecret=<VALIDAT3B_JWT_SECRET de validat3b/.env>` y, opcional, `validat3b.apiUrl=<otra URL>`. Para probar contra un servidor local en un celular por USB: `adb reverse tcp:8001 tcp:8001` y `adb shell am start -n com.example.a3bapp/.MainActivity --es api_url http://localhost:8001` (solo en builds debug).
- [PROPUESTA_SOLUCION.md](PROPUESTA_SOLUCION.md): análisis de los datos y diseño de la solución.

Los datos del reto (`Validat3B_desarrollo_*`) no se incluyen en el repositorio; colócalos en esta carpeta para ejecutar.
