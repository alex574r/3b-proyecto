package com.example.a3bapp

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@Composable
fun rememberThumbFile(path: String): ImageBitmap? =
    produceState<ImageBitmap?>(null, path) {
        value = null
        value = withContext(Dispatchers.IO) { runCatching { ValidatApi.thumbFile(path).asImageBitmap() }.getOrNull() }
    }.value

@Composable
fun MiniFoto(path: String, label: String, modifier: Modifier = Modifier) {
    val bmp = rememberThumbFile(path)
    Box(modifier.clip(RoundedCornerShape(8.dp)).background(MaterialTheme.colorScheme.surfaceVariant)) {
        if (bmp != null) {
            Image(bmp, contentDescription = "Foto de $label", contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize())
        }
    }
}

@Composable
fun HistorialScreen(modifier: Modifier = Modifier) {
    val ctx = LocalContext.current
    val items by CapturaRepo.observarTodas(ctx).collectAsStateWithLifecycle(emptyList())
    val enProceso by CapturaRepo.enProceso.collectAsStateWithLifecycle()
    val pendientes = items.count { it.estado == Estado.PENDIENTE }
    var abierta by rememberSaveable { mutableStateOf<Long?>(null) }

    LazyColumn(
        modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        item { Text("Historial", style = MaterialTheme.typography.headlineSmall) }
        if (pendientes > 0) {
            item {
                Button(onClick = { CapturaRepo.sincronizarYa(ctx) }) {
                    Icon(Icons.Default.Refresh, contentDescription = null, modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(8.dp))
                    Text("Enviar pendientes ($pendientes)")
                }
            }
        }
        if (items.isEmpty()) {
            item { Text("Aún no hay análisis. Cada captura que analices aparece aquí, también las que se guardan sin conexión.") }
        }
        items(items, key = { it.id }) { c ->
            CapturaItem(c, expandida = abierta == c.id, enviando = c.id in enProceso) {
                abierta = if (abierta == c.id) null else c.id
            }
        }
    }
}

private val formatoFecha = SimpleDateFormat("dd/MM/yyyy HH:mm", Locale.getDefault())

@Composable
fun CapturaItem(c: Captura, expandida: Boolean, enviando: Boolean, onToggle: () -> Unit) {
    val ctx = LocalContext.current
    val colores = MaterialTheme.colorScheme
    val (icono, color, estado) = when {
        c.estado == Estado.PENDIENTE -> Triple(Icons.Default.Refresh, colores.tertiary, if (enviando) "Enviando…" else "Pendiente de enviar")
        c.estado == Estado.ERROR -> Triple(Icons.Default.Info, colores.error, "Error")
        c.decision == "aprobada" -> Triple(Icons.Default.CheckCircle, colores.secondary, "Aprobada")
        c.decision == "rechazada" -> Triple(Icons.Default.Close, colores.error, "Rechazada")
        else -> Triple(Icons.Default.Warning, colores.tertiary, "Revisión manual")
    }
    val respuesta = remember(c.resultadoJson) { c.resultadoJson?.let { runCatching { JSONObject(it) }.getOrNull() } }
    val oferta = respuesta?.num("precio_descuento")
    Card(Modifier.fillMaxWidth().clickable(onClick = onToggle)) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                MiniFoto(c.producto, "producto", Modifier.size(56.dp))
                Column(Modifier.weight(1f)) {
                    Text(c.nombre.ifBlank { "Sin nombre" }, style = MaterialTheme.typography.titleMedium, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text("${c.tienda.ifBlank { "—" }} · ${formatoFecha.format(Date(c.creadaEn))}", style = MaterialTheme.typography.bodySmall)
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(icono, contentDescription = estado, tint = color, modifier = Modifier.size(16.dp))
                        Spacer(Modifier.width(4.dp))
                        Text(estado + (c.motivo?.let { " · $it" } ?: ""), style = MaterialTheme.typography.bodySmall)
                    }
                    oferta?.let {
                        Text("Oferta ${pesos(it)}", color = colores.primary, style = MaterialTheme.typography.labelMedium)
                    }
                }
            }
            if (expandida) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf("Fachada" to c.fachada, "Producto" to c.producto, "Etiqueta" to c.etiqueta).forEach { (n, ruta) ->
                        Column(Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally) {
                            MiniFoto(ruta, n, Modifier.fillMaxWidth().aspectRatio(0.75f))
                            Text(n, style = MaterialTheme.typography.labelSmall)
                        }
                    }
                }
                listOf(
                    "Tienda" to c.tienda, "Código" to c.barcode, "Precio" to c.precio, "Marca" to c.marca,
                    "Producto" to c.nombre, "Contenido" to "${c.contenido} ${c.unidad}".trim(),
                ).filter { it.second.isNotBlank() }.forEach { Text("${it.first}: ${it.second}", style = MaterialTheme.typography.bodyMedium) }
                if (c.estado != Estado.ENVIADA) {
                    Text("Intentos: ${c.intentos}", style = MaterialTheme.typography.bodySmall)
                    c.error?.let { Text("Último error: $it", color = colores.error, style = MaterialTheme.typography.bodySmall) }
                }
                respuesta?.let { ResultadoCard(it) }
                c.resultadoJson?.let { RespuestaJson(it) }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (c.estado != Estado.ENVIADA) {
                        Button(enabled = !enviando, onClick = { CapturaRepo.enviarYa(ctx, c.id, manual = true) }) {
                            Icon(Icons.Default.Refresh, contentDescription = null, modifier = Modifier.size(18.dp))
                            Spacer(Modifier.width(8.dp))
                            Text("Reintentar")
                        }
                    }
                    OutlinedButton(onClick = { CapturaRepo.borrarYa(ctx, c.id) }) {
                        Icon(Icons.Default.Delete, contentDescription = null, modifier = Modifier.size(18.dp))
                        Spacer(Modifier.width(8.dp))
                        Text("Eliminar")
                    }
                }
            }
        }
    }
}
