package com.example.a3bapp

import androidx.activity.compose.BackHandler
import androidx.annotation.DrawableRes
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.example.a3bapp.ui.theme.Canvas as Fondo
import com.example.a3bapp.ui.theme.Danger
import com.example.a3bapp.ui.theme.Ink
import com.example.a3bapp.ui.theme.Line
import com.example.a3bapp.ui.theme.Muted
import com.example.a3bapp.ui.theme.Paper
import com.example.a3bapp.ui.theme.Success
import com.example.a3bapp.ui.theme.Wash
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.util.Locale

@Composable
fun Icono(@DrawableRes recurso: Int, modifier: Modifier = Modifier, descripcion: String? = null) {
    Icon(painterResource(recurso), descripcion, modifier.then(Modifier.size(20.dp)))
}

@Composable
fun EncabezadoCaptura(
    titulo: String,
    volver: (() -> Unit)? = null,
    modifier: Modifier = Modifier,
    acciones: @Composable () -> Unit = {},
    contenido: @Composable () -> Unit,
) {
    Box(
        modifier.fillMaxSize().background(Brush.verticalGradient(listOf(Fondo, Paper, Fondo))).imePadding(),
        contentAlignment = Alignment.TopCenter,
    ) {
        Column(Modifier.widthIn(max = 560.dp).fillMaxSize().padding(horizontal = 20.dp, vertical = 12.dp)) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                    Image(painterResource(R.drawable.figma_logo), "Tiendas 3B", Modifier.size(35.dp).clip(RoundedCornerShape(10.dp)))
                    Text("Validat3B", style = MaterialTheme.typography.titleMedium)
                }
                if (volver == null) Icono(R.drawable.figma_shield)
                else OutlinedButton(onClick = volver, shape = MaterialTheme.shapes.small, border = BorderStroke(1.dp, Line)) {
                    Text("‹ Volver", color = Ink)
                }
            }
            HorizontalDivider(Modifier.padding(top = 10.dp), color = Line)
            key(titulo) {
                Column(
                    Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(vertical = 16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) { contenido() }
            }
            acciones()
        }
    }
}

@Composable
fun Acciones(
    principal: String,
    onPrincipal: () -> Unit,
    secundaria: String? = null,
    onSecundaria: () -> Unit = {},
    principalHabilitada: Boolean = true,
) {
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Button(
            onClick = onPrincipal, enabled = principalHabilitada,
            modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp), shape = MaterialTheme.shapes.small,
        ) { Text(principal) }
        if (secundaria != null) {
            OutlinedButton(
                onClick = onSecundaria, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
                shape = MaterialTheme.shapes.small, border = BorderStroke(1.dp, Line),
            ) { Text(secundaria, color = Ink) }
        }
    }
}

@Composable
fun Titular(seccion: String?, titulo: String, descripcion: String? = null) {
    Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
        seccion?.let { Text(it.uppercase(Locale.ROOT), style = MaterialTheme.typography.labelSmall, color = Danger) }
        Text(titulo, style = MaterialTheme.typography.headlineLarge)
        descripcion?.let { Text(it, color = Muted) }
    }
}

@Composable
fun Panel(contenido: @Composable () -> Unit) {
    Surface(
        modifier = Modifier.fillMaxWidth(), color = Paper.copy(alpha = 0.83f),
        shape = MaterialTheme.shapes.medium, border = BorderStroke(1.dp, Line),
    ) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) { contenido() }
    }
}

@Composable
fun PanelAviso(@DrawableRes icono: Int, titulo: String, detalle: String) {
    Panel {
        Icono(icono)
        Text(titulo, style = MaterialTheme.typography.titleMedium)
        Text(detalle, color = Muted)
    }
}

@Composable
fun Pasos(activa: Evidencia) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Evidencia.entries.forEach { tipo ->
            Surface(
                Modifier.weight(1f), shape = RoundedCornerShape(30.dp),
                color = if (tipo == activa) Ink else Wash,
                contentColor = if (tipo == activa) Paper else Muted,
            ) {
                Text("${tipo.ordinal + 1} ${tipo.titulo}", Modifier.padding(vertical = 8.dp), textAlign = TextAlign.Center,
                    style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

@Composable
fun Encuadre(
    guia: String? = null,
    rotulo: String? = null,
    evidencia: Evidencia? = null,
    imagen: @Composable BoxScope.() -> Unit,
) {
    Box(Modifier.fillMaxWidth().aspectRatio(1.23f).clip(MaterialTheme.shapes.medium).background(Wash)) {
        imagen()
        if (guia != null) {
            Canvas(Modifier.fillMaxSize()) {
                val ancho = if (evidencia == Evidencia.Producto) .62f else .84f
                val alto = when (evidencia) { Evidencia.Producto -> .70f; Evidencia.Etiqueta -> .30f; else -> .45f }
                drawRoundRect(
                    Paper,
                    topLeft = Offset(size.width * (1 - ancho) / 2, size.height * (1 - alto) / 2),
                    size = Size(size.width * ancho, size.height * alto),
                    cornerRadius = CornerRadius(13.dp.toPx()),
                    style = Stroke(2.dp.toPx(), pathEffect = PathEffect.dashPathEffect(floatArrayOf(7.dp.toPx(), 4.dp.toPx()))),
                )
            }
            if (guia.isNotBlank()) {
                Text(guia, Modifier.align(Alignment.BottomCenter).padding(13.dp).clip(MaterialTheme.shapes.small)
                    .background(Ink).padding(horizontal = 22.dp, vertical = 6.dp), color = Paper, style = MaterialTheme.typography.bodySmall)
            }
        }
        rotulo?.let {
            Text(it, Modifier.align(Alignment.TopStart).padding(12.dp).clip(MaterialTheme.shapes.small)
                .background(Ink).padding(horizontal = 8.dp, vertical = 5.dp), color = Paper, style = MaterialTheme.typography.labelSmall)
        }
    }
}

@Composable
private fun FotoDemo(archivo: String, descripcion: String?, modifier: Modifier = Modifier) {
    val assets = LocalContext.current.assets
    val imagen by produceState<ImageBitmap?>(null, archivo) {
        value = withContext(Dispatchers.IO) {
            runCatching {
                val options = android.graphics.BitmapFactory.Options().apply { inSampleSize = 2 }
                assets.open(archivo).use { android.graphics.BitmapFactory.decodeStream(it, null, options)?.asImageBitmap() }
            }.getOrNull()
        }
    }
    imagen?.let { Image(it, descripcion, modifier, contentScale = ContentScale.Crop) }
}

@Composable
fun CapturaFlujo(modelo: CapturaUiModel, modifier: Modifier = Modifier) {
    val id = modelo.id
    val capturaObservada by remember(id) { modelo.observar(id) }.collectAsStateWithLifecycle(null)
    val actual = capturaObservada?.takeIf { it.id == id }
    val enProceso by modelo.enProceso.collectAsStateWithLifecycle()
    val casoDemo = rememberDatosDemo()
    BackHandler(enabled = modelo.pantalla != Pantalla.Inicio) { modelo.volver() }
    LaunchedEffect(actual?.id, actual?.estado) {
        actual?.takeIf { it.estado == Estado.ENVIADA }?.let(modelo::autollenar)
    }

    Box(modifier.fillMaxSize()) {
        key(modelo.pantalla) {
            when (modelo.pantalla) {
                Pantalla.Inicio -> Inicio(modelo)
                Pantalla.Guia -> Guia(modelo)
                Pantalla.Camara -> CamaraPantalla(modelo)
                Pantalla.Galeria -> GaleriaPantalla(modelo)
                Pantalla.VistaPrevia -> VistaPrevia(modelo)
                Pantalla.Revision -> Revision(modelo, actual, false, casoDemo)
                Pantalla.Analisis -> Analisis(modelo, actual, id in enProceso)
                Pantalla.Demo -> CasosDemo(modelo, casoDemo)
                Pantalla.DemoAnalisis, Pantalla.DemoResultado -> ResultadoDemo(modelo, casoDemo)
                Pantalla.DemoRevision -> Revision(modelo, null, true, casoDemo)
                Pantalla.DemoRed -> RedDemo(modelo)
            }
        }
    }
}

@Composable
private fun Inicio(modelo: CapturaUiModel) {
    EncabezadoCaptura("Inicio", acciones = {
        Acciones(
            if (modelo.puedeContinuar) "Continuar captura" else "Comenzar captura",
            onPrincipal = modelo::continuar,
            secundaria = "Casos de demostración", onSecundaria = { modelo.simular(Pantalla.Demo) },
        )
    }) {
        modelo.mensaje?.let { Text(it, color = Ink) }
        Titular("Captura de evidencias", "Verifica un precio en tienda", "Toma tres fotos y consulta el dictamen de tu captura.")
        Image(painterResource(R.drawable.figma_banner), "Tiendas 3B", Modifier.fillMaxWidth().aspectRatio(1.98f)
            .clip(MaterialTheme.shapes.medium), contentScale = ContentScale.Crop)
        Panel {
            Evidencia.entries.forEach { tipo ->
                Surface(shape = MaterialTheme.shapes.small, border = BorderStroke(1.dp, Line), color = Paper) {
                    Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 10.dp), horizontalArrangement = Arrangement.spacedBy(10.dp),
                        verticalAlignment = Alignment.CenterVertically) {
                        Icono(R.drawable.figma_camera)
                        Column {
                            Text(tipo.titulo, style = MaterialTheme.typography.titleSmall)
                            Text("Foto obligatoria", style = MaterialTheme.typography.bodySmall, color = Muted)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun Guia(modelo: CapturaUiModel) {
    val tipo = modelo.evidencia
    EncabezadoCaptura(tipo.titulo, modelo::volver, acciones = {
        Acciones("Tomar foto", onPrincipal = { modelo.ir(Pantalla.Camara) }, "Abrir galería", { modelo.ir(Pantalla.Galeria) })
    }) {
        Pasos(tipo)
        Titular("Foto ${tipo.ordinal + 1} de 3", "Foto de ${tipo.titulo.lowercase()}", tipo.instruccion)
        Encuadre(tipo.objetivo, "GUÍA DE CAPTURA", tipo) { FotoDemo(tipo.ejemplo, "Ejemplo de ${tipo.titulo.lowercase()}", Modifier.fillMaxSize()) }
        PanelAviso(R.drawable.figma_alert, "Antes de continuar", tipo.cuidado)
    }
}

@Composable
private fun VistaPrevia(modelo: CapturaUiModel) {
    val tipo = modelo.evidencia
    EncabezadoCaptura("Vista previa", modelo::volver, acciones = {
        Acciones(
            if (modelo.reemplazo) "Guardar reemplazo" else "Usar esta foto", onPrincipal = modelo::aceptarFoto,
            if (modelo.reemplazo) "Repetir foto" else "Reemplazar foto",
            onSecundaria = { modelo.descartarCandidata(); modelo.ir(Pantalla.Camara) },
        )
    }) {
        if (!modelo.reemplazo) Pasos(tipo)
        Titular("Vista previa", if (modelo.reemplazo) "Confirma el reemplazo" else "Revisa la foto", tipo.instruccion)
        Encuadre("") { modelo.candidata?.let { MiniFoto(it, tipo.titulo, Modifier.fillMaxSize()) } }
        if (!modelo.reemplazo) PanelAviso(R.drawable.figma_check, "Foto lista", "Confirma si el elemento solicitado se ve con claridad.")
    }
}

@Composable
private fun TarjetasFotos(modelo: CapturaUiModel, demostracion: Boolean) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Evidencia.entries.forEach { tipo ->
            val foto = modelo.fotos[tipo.ordinal]
            val ficha: @Composable () -> Unit = {
                Column(Modifier.padding(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    val preview = Modifier.fillMaxWidth().aspectRatio(2.12f).clip(RoundedCornerShape(6.dp)).background(Wash)
                    if (demostracion) FotoDemo(tipo.ejemplo, tipo.titulo, preview) else MiniFoto(foto, tipo.titulo, preview)
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text(tipo.titulo, style = MaterialTheme.typography.labelMedium)
                        if (!demostracion) Icono(R.drawable.figma_edit, Modifier.size(12.dp), "Editar")
                    }
                }
            }
            val shape = MaterialTheme.shapes.small
            val borde = BorderStroke(1.dp, Line)
            if (!demostracion) {
                Surface(onClick = { modelo.abrirEvidencia(tipo, true) }, modifier = Modifier.weight(1f), color = Paper,
                    shape = shape, border = borde, content = ficha)
            } else Surface(Modifier.weight(1f), color = Paper, shape = shape, border = borde, content = ficha)
        }
    }
}

@Composable
private fun Revision(modelo: CapturaUiModel, captura: Captura?, demo: Boolean, datosDemo: JSONObject?) {
    val ejemplo = datosDemo?.optJSONObject("ejemplo")
    var precioDemo by rememberSaveable { mutableStateOf("abc") }
    val errorPrecio = if (demo) !precioValido(precioDemo) else modelo.precioInvalido
    val focoPrecio = remember { FocusRequester() }
    LaunchedEffect(errorPrecio) { if (errorPrecio && !demo) focoPrecio.requestFocus() }
    EncabezadoCaptura("Revisión", modelo::volver, acciones = {
        if (demo) {
            Acciones(
                if (errorPrecio) "Corregir precio" else "Analizar captura",
                onPrincipal = { if (errorPrecio) focoPrecio.requestFocus() else modelo.simular(Pantalla.DemoAnalisis, "CAP-000145") },
                secundaria = "Simular error de red", onSecundaria = { modelo.simular(Pantalla.DemoRed) },
            )
        } else {
            Acciones(
                if (errorPrecio) "Corregir precio" else if (modelo.guardando) "Guardando…" else "Guardar captura",
                onPrincipal = { if (errorPrecio) focoPrecio.requestFocus() else modelo.analizar(captura) },
                principalHabilitada = modelo.fotosListas == Evidencia.entries.size && !modelo.guardando,
            )
        }
    }) {
        if (errorPrecio) Titular("Error de validación", "Revisa el precio", "Escribe un importe válido en MXN o deja el campo vacío.")
        else Titular("Datos de captura", "Revisa y envía", "Revisa las tres fotos y añade datos del producto si los tienes.")
        TarjetasFotos(modelo, demo)
        Text("Datos opcionales", style = MaterialTheme.typography.titleMedium)
        CampoCaptura.entries.chunked(2).forEach { fila ->
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                fila.forEach { campo ->
                    val esPrecio = campo == CampoCaptura.Precio
                    val valor = if (!demo) modelo.campos[campo.ordinal] else if (esPrecio) precioDemo else ejemplo?.str(campo.clave).orEmpty()
                    OutlinedTextField(
                        value = valor,
                        onValueChange = { if (!demo) modelo.campo(campo, it) else if (esPrecio) precioDemo = it },
                        modifier = Modifier.weight(1f).then(if (esPrecio) Modifier.focusRequester(focoPrecio) else Modifier),
                        label = { Text(campo.titulo, style = MaterialTheme.typography.labelMedium) },
                        singleLine = true,
                        isError = esPrecio && errorPrecio,
                        readOnly = demo && !esPrecio,
                        keyboardOptions = KeyboardOptions(keyboardType = when (campo) {
                            CampoCaptura.Precio, CampoCaptura.Cantidad -> KeyboardType.Decimal
                            CampoCaptura.Codigo -> KeyboardType.Number
                            else -> KeyboardType.Text
                        }),
                    )
                }
            }
            if (fila.first() == CampoCaptura.Precio && errorPrecio) {
                Text("Usa un importe numérico, por ejemplo 42.50.", color = Danger, style = MaterialTheme.typography.bodySmall)
            }
        }
        Text("✓  ${if (demo) 3 else modelo.fotosListas} de 3 fotos listas", color = Success, style = MaterialTheme.typography.bodySmall)
        modelo.mensaje?.let { Text(it, color = Danger) }
    }
}

@Composable
private fun rememberDatosDemo(): JSONObject? {
    val assets = LocalContext.current.assets
    return remember(assets) { runCatching { JSONObject(assets.open("cases.json").bufferedReader().use { it.readText() }) }.getOrNull() }
}

@Composable
private fun CasosDemo(modelo: CapturaUiModel, datos: JSONObject?) {
    EncabezadoCaptura("Casos de demostración", modelo::volver, acciones = {
        Acciones("Simular precio inválido", onPrincipal = { modelo.simular(Pantalla.DemoRevision) },
            secundaria = "Volver a captura", onSecundaria = modelo::volver)
    }) {
        Titular("Datos simulados", "Casos de demostración", "Explora las mismas capturas en el panel de auditoría.")
        val casos = datos?.optJSONArray("casos")
        if (casos == null) Text("No se pudieron cargar los casos de demostración.")
        else repeat(casos.length()) { indice ->
            val caso = casos.getJSONObject(indice)
            val id = caso.str("capture_id")
            Surface(
                onClick = { modelo.simular(Pantalla.DemoAnalisis, id) }, modifier = Modifier.fillMaxWidth(),
                shape = MaterialTheme.shapes.small, color = Paper, border = BorderStroke(1.dp, Line),
            ) {
                Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(caso.str("titulo"), style = MaterialTheme.typography.titleSmall)
                        Identificador(id)
                    }
                    Icono(R.drawable.figma_chevron)
                }
            }
        }
    }
}

@Composable
private fun ResultadoDemo(modelo: CapturaUiModel, datos: JSONObject?) {
    val casos = datos?.optJSONArray("casos")
    val caso = remember(casos, modelo.simulacion) {
        (0 until (casos?.length() ?: 0)).mapNotNull { casos?.optJSONObject(it) }
            .firstOrNull { it.str("capture_id") == modelo.simulacion }
    }
    if (caso == null) {
        EncabezadoCaptura("Caso de demostración", modelo::volver) { Text("Caso no disponible.") }
        return
    }
    if (modelo.pantalla == Pantalla.DemoAnalisis) {
        var progreso by remember { mutableStateOf(0.25f) }
        LaunchedEffect(caso) {
            delay(300)
            progreso = 0.7f
            delay(650)
            modelo.simular(Pantalla.DemoResultado, modelo.simulacion)
        }
        PantallaProcesando(modelo::volver, modelo.simulacion, progreso)
    } else {
        EncabezadoCaptura("Dictamen de demostración", modelo::volver, acciones = {
            Acciones("Nueva captura", onPrincipal = { modelo.ir(Pantalla.Demo) },
                secundaria = "Recapturar", onSecundaria = { modelo.simular(Pantalla.DemoRevision) })
        }) { ResultadoCard(caso) }
    }
}

@Composable
private fun RedDemo(modelo: CapturaUiModel) {
    EncabezadoCaptura("Error de red simulado", modelo::volver, acciones = {
        Acciones("Reintentar análisis", onPrincipal = { modelo.simular(Pantalla.DemoAnalisis, "CAP-000145") },
            secundaria = "Volver a la captura", onSecundaria = { modelo.simular(Pantalla.DemoRevision) })
    }) {
        Titular("Error de red simulado", "Sin conexión", "La captura quedó lista para reintentar el envío.")
        PanelAviso(R.drawable.figma_wifi, "3 fotos y datos conservados", "Comprueba tu conexión y vuelve a intentar el análisis.")
        TarjetasFotos(modelo, demostracion = true)
    }
}

@Composable
private fun Analisis(modelo: CapturaUiModel, actual: Captura?, enviando: Boolean) {
    if (modelo.guardando || enviando) {
        PantallaProcesando(modelo::volver, actual?.id?.toString())
        return
    }
    if (actual == null) {
        EncabezadoCaptura("Captura", modelo::volver, acciones = {
            Acciones("Volver a captura", onPrincipal = { modelo.ir(Pantalla.Revision) })
        }) { Titular(null, "Captura no disponible", "Puedes revisar el borrador o consultar el historial.") }
        return
    }
    if (actual.estado != Estado.ENVIADA) {
        val pendiente = actual.estado == Estado.PENDIENTE
        EncabezadoCaptura("Error de envío", modelo::volver, acciones = {
            Acciones("Reintentar análisis", onPrincipal = { modelo.reintentar(actual.id) },
                secundaria = "Volver a la captura", onSecundaria = { modelo.ir(Pantalla.Revision) })
        }) {
            Titular(
                if (pendiente) "Envío pendiente" else "Error de envío",
                if (actual.error == "Sin conexión") "Sin conexión" else if (pendiente) "Guardada sin enviar" else "No se pudo analizar",
                if (pendiente) "La captura está en el historial y se enviará automáticamente al recuperar conexión."
                else "Tu captura se conservó y puedes volver a intentar el envío.",
            )
            PanelAviso(if (pendiente) R.drawable.figma_wifi else R.drawable.figma_alert, "3 fotos y datos conservados", actual.error.orEmpty())
            TarjetasFotos(modelo, demostracion = false)
        }
        return
    }
    val resultado = remember(actual.resultadoJson) {
        actual.resultadoJson?.let { runCatching { JSONObject(it) }.getOrNull() }
    }
    EncabezadoCaptura("Dictamen", modelo::volver, acciones = {
        Acciones("Nueva captura", onPrincipal = modelo::nueva, secundaria = "Recapturar",
            onSecundaria = { modelo.ir(Pantalla.Revision) })
    }) {
        if (resultado == null) Titular("Dictamen del motor", "Captura analizada")
        else ResultadoCard(resultado)
        actual.resultadoJson?.let { RespuestaJson(it) }
    }
}
