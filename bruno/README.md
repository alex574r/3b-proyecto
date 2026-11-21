# Colección Bruno de la API Validat3B

Abrir en Bruno: **Open Collection** → esta carpeta (`bruno/`). Contrato completo: [../validat3b/API.md](../validat3b/API.md).

1. Elige el entorno `produccion` (`https://api.jamp.digital`) o `local` (`http://localhost:8000`).
2. En el entorno, rellena el secreto `token` con el valor de `VALIDAT3B_TOKEN` (`validat3b\.env`). Bruno no lo guarda en los archivos.
3. Ejecuta `01 Health` y luego `02 Validar`. `03` lee fotos desde `photosDir` y requiere cambiar el JavaScript Sandbox de la colección a **Developer Mode** (ajustes de la colección → Security); en Safe Mode falla con `Cannot find module fs`.
4. `04`–`06` verifican los errores (401, 400, 404) y no gastan tokens.

`02` y `03` llaman a Haiku si el servidor corre con él (~3.5k tokens cada una).
