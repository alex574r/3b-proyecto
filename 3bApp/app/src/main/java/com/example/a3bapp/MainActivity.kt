package com.example.a3bapp

import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.example.a3bapp.ui.theme._3bAppTheme
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            _3bAppTheme {
                Scaffold(modifier = Modifier.fillMaxSize()) { innerPadding ->
                    ValidarScreen(Modifier.padding(innerPadding))
                }
            }
        }
    }
}

@Composable
fun Campo(label: String, value: String, onChange: (String) -> Unit, modifier: Modifier = Modifier.fillMaxWidth()) =
    OutlinedTextField(value = value, onValueChange = onChange, label = { Text(label) }, singleLine = true, modifier = modifier)

@Composable
fun FotoButton(label: String, uri: Uri?, modifier: Modifier = Modifier, onPick: (Uri) -> Unit) {
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { it?.let(onPick) }
    OutlinedButton(modifier = modifier, onClick = {
        launcher.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
    }) { Text(if (uri == null) label else "✓ $label", maxLines = 1) }
}

@Composable
fun ValidarScreen(modifier: Modifier = Modifier) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    // Por defecto, la API pública vía túnel de Cloudflare (validat3b/iniciar_publico.ps1). Para pruebas locales:
    // http://localhost:8000 con `adb reverse tcp:8000 tcp:8000`, o 10.0.2.2:8000 en el emulador
    var url by rememberSaveable { mutableStateOf("https://api.jamp.digital") }
    var token by rememberSaveable { mutableStateOf("") }
    var tienda by rememberSaveable { mutableStateOf("") }
    var barcode by rememberSaveable { mutableStateOf("") }
    var precio by rememberSaveable { mutableStateOf("") }
    var marca by rememberSaveable { mutableStateOf("") }
    var producto by rememberSaveable { mutableStateOf("") }
    var contenido by rememberSaveable { mutableStateOf("") }
    var unidad by rememberSaveable { mutableStateOf("gramo") }
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
        Campo("URL del servidor", url, { url = it })
        Campo("Token (X-Api-Key)", token, { token = it })
        Campo("Tienda / cadena", tienda, { tienda = it })
        Campo("Código de barras", barcode, { barcode = it })
        Campo("Precio capturado", precio, { precio = it })
        Campo("Marca", marca, { marca = it })
        Campo("Producto esperado", producto, { producto = it })
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Campo("Contenido", contenido, { contenido = it }, Modifier.weight(1f))
            Campo("Unidad", unidad, { unidad = it }, Modifier.weight(1f))
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FotoButton("Fachada", fachada, Modifier.weight(1f)) { fachada = it }
            FotoButton("Producto", foto, Modifier.weight(1f)) { foto = it }
            FotoButton("Etiqueta", etiqueta, Modifier.weight(1f)) { etiqueta = it }
        }
        Button(
            enabled = !loading && tienda.isNotBlank() && fachada != null && foto != null && etiqueta != null,
            onClick = {
                loading = true; error = null; result = null
                scope.launch {
                    try {
                        result = withContext(Dispatchers.IO) {
                            val fields = JSONObject()
                                .put("capture_store_name", tienda).put("capture_barcode", barcode)
                                .put("capture_price", precio).put("capture_brand", marca)
                                .put("product_name", producto).put("unit_quantity_product", contenido)
                                .put("unit_product", unidad)
                            val cr = ctx.contentResolver
                            val photos = mapOf(
                                "facade" to ValidatApi.jpeg(cr, fachada!!),
                                "product" to ValidatApi.jpeg(cr, foto!!),
                                "shelf" to ValidatApi.jpeg(cr, etiqueta!!),
                            )
                            ValidatApi.validar(url, token, fields, photos)
                        }
                    } catch (e: Exception) {
                        error = e.message ?: e.toString()
                    } finally {
                        loading = false
                    }
                }
            },
        ) { Text("Validar") }

        if (loading) CircularProgressIndicator()
        error?.let { Text("Error: $it", color = MaterialTheme.colorScheme.error) }
        result?.let { r ->
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(r.getString("decision").uppercase(), style = MaterialTheme.typography.titleLarge)
                    Text("Confianza ${r.getDouble("confidence_score")} · ${r.getString("reason_code")}")
                    val v = r.getJSONObject("validaciones")
                    v.keys().forEach { Text("$it: ${v.getString(it)}") }
                    Text("Precio detectado: ${r.opt("precio_detectado")}")
                    Text("Código detectado: ${r.opt("codigo_barras_detectado")}")
                    Text(r.getString("explicacion"))
                }
            }
        }
    }
}
