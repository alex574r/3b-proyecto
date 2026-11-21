# 3b-proyecto

Motor de validación de capturas de precio (reto Validat3B): recibe las 3 fotos de una captura y sus datos, y devuelve un JSON
auditable con la decisión (`aprobada`, `rechazada` o `revision_manual`).

| Carpeta | Qué es |
|---|---|
| [validat3b/](validat3b/) | Motor (Python), API HTTP (`server.py`), ventana de escritorio y línea de comandos. Más detalle en su README y en [API.md](validat3b/API.md). |
| [3bApp/](3bApp/) | App Android (Compose): eliges o tomas las 3 fotos, las envía a la API (`POST /analizar`), llena sola los datos y muestra la decisión y el JSON. Historial en Room; sin red, la captura queda *pendiente* y WorkManager la reenvía. |
| [audit-demo/](audit-demo/) | Panel de gestión y auditoría (demo estática, datos de ejemplo). |
| [bruno/](bruno/) | Colección de Bruno para probar la API. |
| [documentacion/](documentacion/) | Ficha técnica (md, html y pdf) y sus diagramas. |
| [PROPUESTA_SOLUCION.md](PROPUESTA_SOLUCION.md) | Análisis de los datos y diseño de la solución. |

Los datos del reto (`Validat3B_desarrollo_*`) no se incluyen en el repositorio; colócalos en la raíz para correr el motor sobre ellos.

## Cómo correr el proyecto

### Requisitos
- Windows con PowerShell, Git y **Python 3.10+** (probado con 3.12).
- **La llave de Foundry** (`FOUNDRY_API_KEY`): no está en el repo, pídela al equipo. Sin ella el motor solo hace los chequeos locales (`-NoLlm`).
- Para publicar la API en internet: `cloudflared` con el túnel `validat3b` ya creado en tu equipo. Sin túnel, la API corre solo en local.
- Para la app: Android Studio y un teléfono o emulador con Android 13 o superior (`minSdk 33`).

### 1. Clonar e instalar
```powershell
git clone https://github.com/alex574r/3b-proyecto.git
cd 3b-proyecto\validat3b
python -m pip install -r requirements.txt
```

### 2. Variables de entorno
`validat3b/.env` **ya viene en el repo con valores de prueba**: `VALIDAT3B_TOKEN` (token para el header `X-Api-Key`) y
`VALIDAT3B_JWT_SECRET` (secreto con el que la app firma su JWT). Lo lee `iniciar_publico.ps1`; `python server.py` a secas **no** lo lee.
La llave de Foundry nunca va en ese archivo: se define en la sesión.

### 3. Levantar la API
Con túnel de Cloudflare, publicada en `https://api.jamp.digital` (la que usa la app):
```powershell
$env:FOUNDRY_API_KEY = "<llave-de-foundry>"
.\iniciar_publico.ps1
```
Solo en local, sin túnel, en `http://127.0.0.1:8000`:
```powershell
$env:FOUNDRY_API_KEY = "<llave-de-foundry>"
python server.py
```
Agrega `-NoLlm` al script (o `--no-llm` a `server.py`) para no llamar a Foundry. Comprueba que responde:
```powershell
curl.exe http://127.0.0.1:8000/health
```
Debe devolver `{"status": "ok", "llm": true}`. Cada petición se imprime en la consola; **Ctrl+C** la detiene. La API solo responde mientras el
equipo esté encendido y el script corriendo.

### 4. App Android
1. En Android Studio: **Open** y elige la carpeta `3bApp` de este repositorio (no una copia aparte).
2. Crea `3bApp/local.properties` (lo ignora git) con el secreto JWT del paso 2 y, si quieres, otra URL:
   ```properties
   validat3b.jwtSecret=<VALIDAT3B_JWT_SECRET de validat3b/.env>
   validat3b.apiUrl=https://api.jamp.digital
   ```
3. Ejecuta la app (**Run**). Para probar contra la API local desde un celular por USB: `adb reverse tcp:8001 tcp:8001` y
   `adb shell am start -n com.example.a3bapp/.MainActivity --es api_url http://localhost:8001` (solo en builds debug).

### 5. Ventana de escritorio, línea de comandos y pruebas
Desde `validat3b/`:
```powershell
python gui.py                                   # ventana: analiza una carpeta de fotos y exporta un JSON
python run.py --data ..\Validat3B_desarrollo_metadatos\capturas.json --images ..\Validat3B_desarrollo_imagenes --out salida
python evaluate.py --data ..\Validat3B_desarrollo_metadatos\capturas.json --results salida\resultados.json
python tests/test_core.py                       # pruebas sin red (también test_server, test_auto, test_carpeta, test_catalogo)
```

### 6. Panel de auditoría (demo)
```powershell
cd audit-demo
python -m http.server 5500
```
Abre http://localhost:5500 (necesita servidor local porque usa módulos de JavaScript).

### 7. Probar la API a mano
Las peticiones `POST` llevan el header `X-Api-Key` con el valor de `VALIDAT3B_TOKEN`. `GET /health` no pide nada.
- **Bruno:** abre la carpeta `bruno/` (instrucciones en [bruno/README.md](bruno/README.md)).
- **Thunder Client / Postman:** `POST https://api.jamp.digital/analizar`, header `X-Api-Key`, y un body JSON con `facade_b64`, `product_b64` y
  `shelf_b64` (fotos JPEG en base64). La respuesta aparece en el panel de la derecha. Para pasar una foto a base64:
  `[Convert]::ToBase64String([IO.File]::ReadAllBytes("C:\ruta\foto.jpg")) | Set-Clipboard`.
- Contrato completo, campos y errores: [validat3b/API.md](validat3b/API.md).

### Sobre el `.env` del repositorio
Es de pruebas y está versionado a propósito para que cualquiera pueda correr el proyecto. Quien tenga el token puede llamar a la API pública
y **gastar tokens de Foundry**. Al terminar el reto, cambia los dos valores en `validat3b/.env` y el `validat3b.jwtSecret` de la app.
