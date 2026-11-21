package com.example.a3bapp

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
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import com.example.a3bapp.ui.theme._3bAppTheme
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        // Solo en debug: `adb shell am start -n com.example.a3bapp/.MainActivity --es api_url http://localhost:8001`
        // apunta a un servidor local (con `adb reverse`) sin tocar la URL de producción.
        val apiUrl = intent.getStringExtra("api_url")?.takeIf { BuildConfig.DEBUG } ?: BuildConfig.API_URL
        setContent {
            _3bAppTheme {
                Scaffold(modifier = Modifier.fillMaxSize()) { innerPadding ->
                    ValidarScreen(apiUrl, Modifier.padding(innerPadding))
                }
            }
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
    var pending by remember { mutableStateOf<Uri?>(null) }
    val gallery = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { it?.let(onPick) }
    val camera = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { ok -> if (ok) pending?.let(onPick) }
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
                    val dir = File(ctx.cacheDir, "photos").apply { mkdirs() }
                    val file = File(dir, "${label}_${System.currentTimeMillis()}.jpg")
                    pending = FileProvider.getUriForFile(ctx, "${ctx.packageName}.fileprovider", file)
                    camera.launch(pending!!)
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

private fun JSONObject.str(key: String) = if (isNull(key)) "" else optString(key)

@Composable
fun ValidarScreen(apiUrl: String, modifier: Modifier = Modifier) {
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
    var loading by remember { mutableStateOf(false) }
    var result by remember { mutableStateOf<JSONObject?>(null) }
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
            enabled = !loading && fachada != null && foto != null && etiqueta != null,
            onClick = {
                loading = true; error = null; result = null
                scope.launch {
                    try {
                        val text = withContext(Dispatchers.IO) {
                            // lo que ya hay en los campos (autollenado o corregido) viaja como dato del usuario
                            val fields = JSONObject()
                            fun put(k: String, v: String) { if (v.isNotBlank()) fields.put(k, v.trim()) }
                            put("capture_store_name", tienda); put("capture_barcode", barcode); put("capture_price", precio)
                            put("capture_brand", marca); put("product_name", producto)
                            put("unit_quantity_product", contenido); put("unit_product", unidad)
                            val cr = ctx.contentResolver
                            val photos = mapOf(
                                "facade" to ValidatApi.jpeg(cr, fachada!!),
                                "product" to ValidatApi.jpeg(cr, foto!!),
                                "shelf" to ValidatApi.jpeg(cr, etiqueta!!),
                            )
                            ValidatApi.analizar(apiUrl, fields, photos)
                        }
                        val env = JSONObject(text)
                        result = env.getJSONObject("resultado")
                        env.optJSONObject("datos_detectados")?.let { d ->
                            tienda = d.str("capture_store_name"); barcode = d.str("capture_barcode")
                            precio = d.str("capture_price"); marca = d.str("capture_brand")
                            producto = d.str("product_name"); contenido = d.str("unit_quantity_product")
                            unidad = d.str("unit_product")
                        }
                    } catch (e: Exception) {
                        error = e.message ?: e.toString()
                    } finally {
                        loading = false
                    }
                }
            },
        ) { Text("Analizar fotos") }

        if (loading) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                CircularProgressIndicator(Modifier.size(24.dp))
                Text("Analizando…")
            }
        }
        error?.let { Text("Error: $it", color = MaterialTheme.colorScheme.error) }
        result?.let { r ->
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    val decision = r.getString("decision")
                    val (icon, tint) = when (decision) {
                        "aprobada" -> Icons.Default.CheckCircle to MaterialTheme.colorScheme.primary
                        "rechazada" -> Icons.Default.Close to MaterialTheme.colorScheme.error
                        else -> Icons.Default.Warning to MaterialTheme.colorScheme.tertiary
                    }
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Icon(icon, contentDescription = decision, tint = tint)
                        Text(decision.replace('_', ' ').uppercase(), style = MaterialTheme.typography.titleLarge)
                    }
                    Text("Confianza ${r.getDouble("confidence_score")} · ${r.getString("reason_code")}")
                    val v = r.getJSONObject("validaciones")
                    v.keys().forEach { Text("$it: ${v.getString(it)}") }
                    Text(r.getString("explicacion"))
                }
            }
        }

        Text("Datos de la captura", style = MaterialTheme.typography.titleMedium)
        Text(
            "Se llenan solos al analizar las fotos. Puedes corregirlos y volver a analizar.",
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

        result?.let { r ->
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text("JSON de respuesta", style = MaterialTheme.typography.titleSmall)
                    SelectionContainer {
                        Text(r.toString(2).replace("\\/", "/"), fontFamily = FontFamily.Monospace, style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
        }
    }
}
