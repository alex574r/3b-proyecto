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

## Arrancar la versión integrada

Desde la raíz, instala las dependencias con Python 3.10 o superior.

```powershell
python -m pip install -r validat3b/requirements.txt
```

En el equipo que opera el túnel, conserva el archivo privado `validat3b/.env` y el directorio `validat3b/salida_api` antes de cambiar de rama. Una rama anterior puede tener el archivo de entorno bajo control de versiones y Git puede retirarlo del directorio al cambiar a `dev`. Guarda la configuración fuera del checkout y restáurala en la rama actual. Configura `VALIDAT3B_TOKEN`, `VALIDAT3B_JWT_SECRET`, la clave del endpoint asignado `FOUNDRY_API_KEY` y, si se usa acceso independiente para los auditores, `VALIDAT3B_AUDIT_TOKEN`.

En Windows, desde la raíz de `dev`, el operador arranca el servicio con `.\validat3b\iniciar_publico.ps1`. Ese script carga `.env` y abre el túnel existente. Al activar esta versión, [el portal del equipo](https://api.jamp.digital/portal/) y `POST /analizar` se sirven en el mismo dominio. Comprueba que `/health` devuelve `llm: true`, que `/portal/` abre y que la bandeja autenticada contiene una captura conocida. El despliegue requiere actualizar ese proceso en el servidor.

Para desarrollo local se puede ejecutar `python validat3b/server.py` con las credenciales configuradas en el entorno del proceso. Su portal está en `http://127.0.0.1:8000/portal/`. El modo `--no-llm` permite probar el flujo sin gastar llamadas. La ventana de escritorio se abre con `python validat3b/gui.py`. La colección [Bruno](bruno/README.md), los [comandos del motor](validat3b/README.md) y el [contrato HTTP](validat3b/API.md) documentan las demás formas de probarlo.

Para mostrar una captura real con el teléfono conectado, sigue el [guion de presentación con el POCO](documentacion/presentacion_poco.md).

El [piloto de mejora de imágenes](experimentos/piloto/README.md) contiene el selector inicial, la segunda versión y sus pruebas de regresión. El [generador de la muestra](documentacion/preparar_muestra.py) prepara las fotos originales del equipo para la exposición sin subirlas al repositorio.
