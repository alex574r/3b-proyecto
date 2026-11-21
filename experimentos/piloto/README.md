# Piloto de recortes de etiquetas

El piloto reproduce el experimento que llevó al selector integrado en el backend. Compara la foto completa, el recorte y el recorte con contraste local. La primera versión se conserva en `linea_base/` para probar los casos en que el recorte perdía una parte del importe. El código usado por la app está en [el motor de etiquetas](../../validat3b/engine/etiqueta.py).

Desde este directorio, con PowerShell y los paquetes de `requirements.txt` instalados, indica la carpeta privada que contiene `capturas.json` y `imagenes/`. Las pruebas sintéticas se pueden ejecutar también sin el dataset.

```powershell
$env:VALIDAT3B_DATOS = Read-Host 'Carpeta con capturas.json e imagenes'
python -m unittest discover -s pruebas -v
.\run_piloto.ps1 -Datos $env:VALIDAT3B_DATOS
python diagnostico_v1.py
python comparar_versiones.py
```

La corrida local genera `muestra_dev.json` antes de comparar versiones. La comparación selecciona la reserva y genera `salida/antes_despues/antes_despues.html`. Si tienes la revisión visual del equipo, colócala junto al script como `revision_visual.csv`. Sin ese archivo, los recortes que requieren anotación quedan pendientes de revisión. Las imágenes, las anotaciones y las salidas generadas se conservan en el equipo. El recorrido anterior funciona sin llamadas al modelo.
