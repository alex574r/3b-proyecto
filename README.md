# 3b-proyecto

Motor de validación de capturas de precio (reto Validat3B).

- [validat3b/](validat3b/): código del motor, instrucciones de uso en su README.
- [3bApp/](3bApp/): app Android (Compose) que envía las 3 fotos y datos a la API (`validat3b/server.py`) y muestra la decisión. Abrir en Android Studio; para un celular por USB, `adb reverse tcp:8000 tcp:8000`.
- [PROPUESTA_SOLUCION.md](PROPUESTA_SOLUCION.md): análisis de los datos y diseño de la solución.

Los datos del reto (`Validat3B_desarrollo_*`) no se incluyen en el repositorio; colócalos en esta carpeta para ejecutar.
