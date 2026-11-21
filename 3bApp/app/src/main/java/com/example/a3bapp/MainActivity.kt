package com.example.a3bapp

import android.content.Intent
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.List
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.saveable.rememberSaveableStateHolder
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.example.a3bapp.ui.theme._3bAppTheme
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.util.Locale
import java.io.File

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        // Solo en debug: `adb shell am start -n com.example.a3bapp/.MainActivity --es api_url http://localhost:8001`
        // apunta a un servidor local (con `adb reverse`); `--es api_url default` vuelve a la URL de producción.
        if (BuildConfig.DEBUG) {
            intent.getStringExtra("api_url")?.let { CapturaRepo.setApiUrl(this, it.takeUnless { u -> u == "default" }) }
        }
        CapturaRepo.retomarPendientes(this)
        setContent { _3bAppTheme { App() } }
    }
}

@Composable
fun App() {
    val ctx = LocalContext.current
    var tab by rememberSaveable { mutableIntStateOf(0) }
    val pendientes by CapturaRepo.contarPendientes(ctx).collectAsState(0)
    val estados = rememberSaveableStateHolder() // cada pestaña conserva lo que el usuario había escrito
    Scaffold(
        modifier = Modifier.fillMaxSize(),
        bottomBar = {
            NavigationBar {
                NavigationBarItem(
                    selected = tab == 0, onClick = { tab = 0 },
                    icon = { Icon(Icons.Default.Search, contentDescription = null) }, label = { Text("Analizar") },
                )
                NavigationBarItem(
                    selected = tab == 1, onClick = { tab = 1 },
                    icon = {
                        BadgedBox(badge = { if (pendientes > 0) Badge { Text("$pendientes") } }) {
                            Icon(Icons.AutoMirrored.Filled.List, contentDescription = null)
                        }
                    },
                    label = { Text("Historial") },
                )
            }
        },
    ) { innerPadding ->
        estados.SaveableStateProvider(tab) {
            if (tab == 0) ValidarScreen(Modifier.padding(innerPadding)) else HistorialScreen(Modifier.padding(innerPadding))
        }
    }
}

@Composable
fun Campo(label: String, value: String, onChange: (String) -> Unit, modifier: Modifier = Modifier.fillMaxWidth()) =
    OutlinedTextField(value = value, onValueChange = onChange, label = { Text(label) }, singleLine = true, modifier = modifier)

@Composable
fun rememberThumb(uri: Uri): ImageBitmap? {
    val cr = LocalContext.current.contentResolver
    return produceState<ImageBitmap?>(null, uri) {
        value = withContext(Dispatchers.IO) { runCatching { ValidatApi.thumb(cr, uri).asImageBitmap() }.getOrNull() }
    }.value
}

/** Casilla de una foto: muestra la miniatura y, al tocarla, deja tomar la foto con la cámara o elegirla de la galería. */
@Composable
fun FotoSlot(label: String, uri: Uri?, modifier: Modifier = Modifier, onPick: (Uri) -> Unit) {
    val ctx = LocalContext.current
    var menu by remember { mutableStateOf(false) }
    val gallery = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { it?.let(onPick) }
    val camera = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        if (result.resultCode == android.app.Activity.RESULT_OK) result.data?.data?.let(onPick)
    }
    val thumb = uri?.let { rememberThumb(it) }
    Column(modifier, horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Box(
            Modifier.fillMaxWidth().aspectRatio(0.75f).clip(RoundedCornerShape(12.dp))
                .background(MaterialTheme.colorScheme.surfaceVariant).clickable { menu = true },
            contentAlignment = Alignment.Center,
        ) {
            if (thumb != null) {
                Image(thumb, contentDescription = "Foto de $label", contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize())
            } else {
                Icon(Icons.Default.Add, contentDescription = "Agregar foto de $label", modifier = Modifier.size(32.dp))
            }
            DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                DropdownMenuItem(text = { Text("Tomar foto") }, onClick = {
                    menu = false
                    camera.launch(Intent(ctx, CamaraGuiada::class.java).putExtra("tipo", label))
                })
                DropdownMenuItem(text = { Text("Elegir de galería") }, onClick = {
                    menu = false
                    gallery.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
                })
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            if (uri != null) {
                Icon(Icons.Default.Check, contentDescription = "Foto elegida", modifier = Modifier.size(16.dp))
                Spacer(Modifier.width(4.dp))
            }
            Text(label, style = MaterialTheme.typography.labelLarge)
        }
    }
}

/** Número del JSON o null (ausente, null o no numérico): el historial guarda respuestas de versiones anteriores sin estos campos. */
fun JSONObject.num(key: String): Double? = if (isNull(key)) null else optDouble(key).takeUnless { it.isNaN() }

fun pesos(v: Double) = String.format(Locale.US, "$%.2f", v)

/**
 * Respuesta del servidor: registro con la forma de capturas.json (decision_esperada, motivo_rechazo, datos del SKU) más el detalle del
 * motor. También muestra el JSON oficial que guardaron versiones anteriores de la app (decision, sin datos del SKU).
 */
@Composable
fun ResultadoCard(r: JSONObject) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            val decision = r.str("decision_esperada").ifEmpty { r.str("decision") }
            val (icon, tint) = when (decision) {
                "aprobada" -> Icons.Default.CheckCircle to MaterialTheme.colorScheme.primary
                "rechazada" -> Icons.Default.Close to MaterialTheme.colorScheme.error
                else -> Icons.Default.Warning to MaterialTheme.colorScheme.tertiary
            }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Icon(icon, contentDescription = decision, tint = tint)
                Text(decision.replace('_', ' ').uppercase(), style = MaterialTheme.typography.titleLarge)
            }
            r.str("motivo_rechazo").takeIf { it.isNotBlank() }?.let {
                Text("Motivo: $it", color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.titleSmall)
            }

            // Precios: el de la etiqueta y, si hay promoción para este producto, el de oferta por pieza
            val etiqueta = r.num("precio_detectado")
            val oferta = r.num("precio_descuento")
            etiqueta?.let { Text("Precio en etiqueta: ${pesos(it)}") }
            oferta?.let {
                Text("Precio de oferta: ${pesos(it)}", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Bold)
            }

            // Producto en el catálogo (solo si el código de barras está en él)
            r.num("id_product")?.let { sku ->
                val ref = r.num("product_price")
                val min = r.num("min_product_price")
                val max = r.num("max_product_price")
                Text(
                    "SKU ${sku.toLong()}" + (ref?.let { " · Referencia ${pesos(it)}" } ?: "") +
                        (if (min != null && max != null) " (rango ${pesos(min)}–${pesos(max)})" else ""),
                    style = MaterialTheme.typography.bodySmall,
                )
                listOf(r.str("product_group"), r.str("product_line")).filter { it.isNotBlank() }.takeIf { it.isNotEmpty() }
                    ?.let { Text(it.joinToString(" · "), style = MaterialTheme.typography.bodySmall) }
            }

            Text("Confianza ${r.optDouble("confidence_score", 0.0)} · ${r.str("reason_code")}", style = MaterialTheme.typography.bodySmall)
            r.optJSONObject("validaciones")?.let { v -> v.keys().forEach { Text("$it: ${v.optString(it)}", style = MaterialTheme.typography.bodySmall) } }
            Text(r.str("explicacion"))
        }
    }
}

@Composable
fun ValidarScreen(modifier: Modifier = Modifier) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    // Los datos de la captura se llenan solos con lo que el servidor detecta en las fotos; se pueden corregir
    var tienda by rememberSaveable { mutableStateOf("") }
    var barcode by rememberSaveable { mutableStateOf("") }
    var precio by rememberSaveable { mutableStateOf("") }
    var marca by rememberSaveable { mutableStateOf("") }
    var producto by rememberSaveable { mutableStateOf("") }
    var contenido by rememberSaveable { mutableStateOf("") }
    var unidad by rememberSaveable { mutableStateOf("") }
    var fachada by rememberSaveable { mutableStateOf<Uri?>(null) }
    var foto by rememberSaveable { mutableStateOf<Uri?>(null) }
    var etiqueta by rememberSaveable { mutableStateOf<Uri?>(null) }
    var guardando by remember { mutableStateOf(false) }
    var aviso by remember { mutableStateOf<String?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    Column(
        modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text("Validar captura", style = MaterialTheme.typography.headlineSmall)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FotoSlot("Fachada", fachada, Modifier.weight(1f)) { fachada = it }
            FotoSlot("Producto", foto, Modifier.weight(1f)) { foto = it }
            FotoSlot("Etiqueta", etiqueta, Modifier.weight(1f)) { etiqueta = it }
        }
        Button(
            enabled = !guardando && fachada != null && foto != null && etiqueta != null,
            onClick = {
                if (guardando) return@Button
                guardando = true
                error = null
                aviso = null
                scope.launch {
                    try {
                        // lo que ya hay en los campos (autollenado o corregido) viaja como dato del usuario
                        val campos = mapOf(
                            "capture_store_name" to tienda, "capture_barcode" to barcode, "capture_price" to precio,
                            "capture_brand" to marca, "product_name" to producto,
                            "unit_quantity_product" to contenido, "unit_product" to unidad,
                        )
                        // primero se guarda en Room (con las fotos); después se intenta enviar
                        CapturaRepo.nueva(ctx, campos, listOf(fachada!!, foto!!, etiqueta!!))
                        fachada = null; foto = null; etiqueta = null
                        tienda = ""; barcode = ""; precio = ""; marca = ""; producto = ""; contenido = ""; unidad = ""
                        aviso = "Captura guardada. Puedes tomar la siguiente."
                    } catch (e: Exception) {
                        error = "No se pudieron guardar las fotos: ${e.message ?: e}"
                    } finally {
                        guardando = false
                    }
                }
            },
        ) { Text(if (guardando) "Guardando…" else "Guardar captura") }
        aviso?.let { Text(it) }
        error?.let { Text(it, color = MaterialTheme.colorScheme.error) }

        Text("Datos de la captura", style = MaterialTheme.typography.titleMedium)
        Text(
            "Campos opcionales. Consulta los datos detectados en el historial.",
            style = MaterialTheme.typography.bodySmall,
        )
        Campo("Tienda / cadena", tienda, { tienda = it })
        Campo("Código de barras", barcode, { barcode = it })
        Campo("Precio capturado", precio, { precio = it })
        Campo("Marca", marca, { marca = it })
        Campo("Producto", producto, { producto = it })
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Campo("Contenido", contenido, { contenido = it }, Modifier.weight(1f))
            Campo("Unidad", unidad, { unidad = it }, Modifier.weight(1f))
        }

    }
}
