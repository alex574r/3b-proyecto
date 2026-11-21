package com.example.a3bapp

import android.Manifest
import android.content.ContentUris
import android.content.Context
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.provider.MediaStore
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.example.a3bapp.ui.theme.Brand
import com.example.a3bapp.ui.theme.Danger
import com.example.a3bapp.ui.theme.Wash
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

private fun Context.permite(permiso: String) =
    ContextCompat.checkSelfPermission(this, permiso) == PackageManager.PERMISSION_GRANTED

/** Refresca permisos y MediaStore al volver de ajustes o del selector de acceso parcial. */
@Composable
private fun recordarReanudacion(): Int {
    var revision by remember { mutableIntStateOf(0) }
    val owner = LocalLifecycleOwner.current
    DisposableEffect(owner) {
        val observer = LifecycleEventObserver { _, event -> if (event == Lifecycle.Event.ON_RESUME) revision++ }
        owner.lifecycle.addObserver(observer)
        onDispose { owner.lifecycle.removeObserver(observer) }
    }
    return revision
}

@Composable
fun CamaraPantalla(modelo: CapturaUiModel) {
    val ctx = LocalContext.current
    val evidencia = modelo.evidencia
    val owner = LocalLifecycleOwner.current
    val reanudacion = recordarReanudacion()
    var permiso by remember(reanudacion) { mutableStateOf(ctx.permite(Manifest.permission.CAMERA)) }
    var solicitado by rememberSaveable { mutableStateOf(false) }
    val pedirPermiso = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { permiso = it }
    LaunchedEffect(Unit) {
        if (!permiso && !solicitado) {
            solicitado = true
            pedirPermiso.launch(Manifest.permission.CAMERA)
        }
    }

    var captura by remember { mutableStateOf<ImageCapture?>(null) }
    var lado by remember { mutableStateOf<String?>(null) }
    var tomando by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val activa = remember { booleanArrayOf(false) }
    val vista = remember(ctx) {
        PreviewView(ctx).apply {
            implementationMode = PreviewView.ImplementationMode.COMPATIBLE
            scaleType = PreviewView.ScaleType.FILL_CENTER
        }
    }
    val executor = remember(ctx) { ContextCompat.getMainExecutor(ctx) }

    DisposableEffect(permiso, owner, vista) {
        activa[0] = permiso
        val proveedor = if (permiso) ProcessCameraProvider.getInstance(ctx) else null
        val preview = Preview.Builder().build().apply { surfaceProvider = vista.surfaceProvider }
        val disparo = ImageCapture.Builder().build()
        var montada = true
        proveedor?.addListener({
            if (montada) {
                runCatching {
                    val camaras = proveedor.get()
                    val selector = if (camaras.hasCamera(CameraSelector.DEFAULT_BACK_CAMERA)) {
                        CameraSelector.DEFAULT_BACK_CAMERA
                    } else {
                        CameraSelector.DEFAULT_FRONT_CAMERA
                    }
                    camaras.bindToLifecycle(owner, selector, preview, disparo)
                    captura = disparo
                    lado = if (selector == CameraSelector.DEFAULT_BACK_CAMERA) "Cámara trasera" else "Cámara frontal"
                    error = null
                }.onFailure { error = "No se pudo abrir la cámara. Puedes elegir una foto de la galería." }
            }
        }, executor)
        onDispose {
            montada = false
            activa[0] = false
            captura = null
            lado = null
            if (proveedor?.isDone == true) runCatching { proveedor.get().unbind(preview, disparo) }
        }
    }

    EncabezadoCaptura(if (modelo.reemplazo) "Edición individual" else "Cámara", modelo::volver, acciones = {
        // Fuera de la zona desplazable: junto al disparador aunque el texto del sistema esté ampliado.
        if (permiso) {
            Text("Sujeta el teléfono sin moverlo.", Modifier.fillMaxWidth().padding(bottom = 8.dp),
                style = MaterialTheme.typography.bodySmall, textAlign = TextAlign.Center)
        }
        Acciones(
            if (permiso) "Tomar foto" else "Permitir cámara",
            principalHabilitada = !tomando && (!permiso || captura != null),
            onPrincipal = {
                if (!permiso) {
                    pedirPermiso.launch(Manifest.permission.CAMERA)
                } else {
                    captura?.let { camara ->
                        val destino = runCatching { modelo.nuevaFoto() }.getOrNull()
                        if (destino == null) {
                            error = "No hay espacio para guardar la foto."
                        } else {
                            tomando = true
                            error = null
                            vista.display?.let { camara.targetRotation = it.rotation }
                            camara.takePicture(ImageCapture.OutputFileOptions.Builder(destino).build(), executor,
                                object : ImageCapture.OnImageSavedCallback {
                                    override fun onImageSaved(output: ImageCapture.OutputFileResults) {
                                        tomando = false
                                        if (activa[0]) modelo.revisarFoto(destino) else destino.delete()
                                    }

                                    override fun onError(exception: ImageCaptureException) {
                                        destino.delete()
                                        tomando = false
                                        error = "No se pudo tomar la foto. Vuelve a intentarlo."
                                    }
                                },
                            )
                        }
                    }
                }
            },
            secundaria = "Abrir galería", onSecundaria = { modelo.ir(Pantalla.Galeria) },
        )
    }) {
        if (!modelo.reemplazo) Pasos(evidencia)
        Titular(
            null,
            if (modelo.reemplazo) "Reemplazar ${evidencia.titulo.lowercase()}" else "Encuadra la ${if (evidencia == Evidencia.Producto) "foto de producto" else evidencia.titulo.lowercase()}",
            // Sin permiso se explica qué buscar; con cámara, la indicación vive sobre la vista previa.
            if (permiso) null else evidencia.instruccion,
        )
        if (permiso) {
            Encuadre(evidencia.objetivo, "CÁMARA", evidencia, evidencia.indicaciones) {
                AndroidView(factory = { vista }, modifier = Modifier.fillMaxSize())
            }
            if (modelo.reemplazo) {
                PanelAviso(R.drawable.figma_edit, "Las otras fotos se conservan", "Toma una nueva foto para sustituir solamente esta evidencia.")
            } else {
                lado?.let { Identificador("${it} · 1×") }
            }
        } else {
            PanelAviso(R.drawable.figma_camera, "Permiso de cámara", "Activa el acceso a la cámara o abre la galería para continuar.")
        }
        error?.let { Text(it, color = Danger) }
    }
}

private fun fotosRecientes(ctx: Context): List<Uri> {
    val album = MediaStore.Images.Media.EXTERNAL_CONTENT_URI
    return buildList {
        ctx.contentResolver.query(
            album,
            arrayOf(MediaStore.Images.Media._ID),
            null,
            null,
            "${MediaStore.Images.Media.DATE_ADDED} DESC, ${MediaStore.Images.Media._ID} DESC",
        )?.use { cursor ->
            while (cursor.moveToNext()) add(ContentUris.withAppendedId(album, cursor.getLong(0)))
        }
    }
}

@Composable
private fun FotoGaleria(uri: Uri, modifier: Modifier = Modifier, descripcion: String? = null) {
    val resolver = LocalContext.current.contentResolver
    val miniatura by produceState<ImageBitmap?>(null, uri) {
        value = null
        value = withContext(Dispatchers.IO) { runCatching { ValidatApi.thumb(resolver, uri).asImageBitmap() }.getOrNull() }
    }
    Box(modifier.background(Wash)) {
        miniatura?.let { Image(it, descripcion, Modifier.fillMaxSize(), contentScale = ContentScale.Crop) }
    }
}

@Composable
fun GaleriaPantalla(modelo: CapturaUiModel) {
    val ctx = LocalContext.current
    val evidencia = modelo.evidencia
    val reanudacion = recordarReanudacion()
    var cambios by remember { mutableIntStateOf(0) }
    var solicitado by rememberSaveable { mutableStateOf(false) }
    val permisos = remember {
        if (Build.VERSION.SDK_INT >= 34) arrayOf(Manifest.permission.READ_MEDIA_IMAGES, Manifest.permission.READ_MEDIA_VISUAL_USER_SELECTED)
        else arrayOf(Manifest.permission.READ_MEDIA_IMAGES)
    }
    val pedirPermisos = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { cambios++ }
    val selector = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri -> uri?.let(modelo::importar) }
    val completo = remember(reanudacion, cambios) { ctx.permite(Manifest.permission.READ_MEDIA_IMAGES) }
    val parcial = remember(reanudacion, cambios) { Build.VERSION.SDK_INT >= 34 && ctx.permite(Manifest.permission.READ_MEDIA_VISUAL_USER_SELECTED) }
    val acceso = completo || parcial
    LaunchedEffect(Unit) {
        if (!solicitado && !acceso) {
            solicitado = true
            pedirPermisos.launch(permisos)
        }
    }
    val resultado by produceState<List<Uri>?>(null, acceso, reanudacion, cambios) {
        value = null
        value = if (acceso) withContext(Dispatchers.IO) { runCatching { fotosRecientes(ctx) }.getOrDefault(emptyList()) } else emptyList()
    }
    val fotos = if (acceso) resultado else emptyList()
    var seleccion by rememberSaveable { mutableStateOf<String?>(null) }
    val elegida = fotos?.firstOrNull { it.toString() == seleccion } ?: fotos?.firstOrNull()
    val abrirSelector = { selector.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)) }
    EncabezadoCaptura("Galería", modelo::volver, acciones = {
        Acciones(
            if (elegida == null) "Elegir con Android" else "Seleccionar foto",
            principalHabilitada = !modelo.guardando,
            onPrincipal = { elegida?.let(modelo::importar) ?: abrirSelector() },
            secundaria = "Abrir cámara", onSecundaria = { if (!modelo.guardando) modelo.ir(Pantalla.Camara) },
        )
    }) {
        Pasos(evidencia)
        Titular(null, "Elegir foto", evidencia.instruccion)
        if (elegida != null) {
            Encuadre { FotoGaleria(elegida, Modifier.fillMaxSize(), "Imagen seleccionada") }
            Text("Imágenes recientes")
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                items(fotos.orEmpty(), key = Uri::toString) { uri ->
                    val marco = RoundedCornerShape(8.dp)
                    FotoGaleria(
                        uri,
                        Modifier.size(64.dp).clip(marco).border(1.dp, if (uri == elegida) Brand else Wash, marco)
                            .clickable(onClickLabel = "Elegir imagen") { seleccion = uri.toString() },
                        if (uri == elegida) "Imagen seleccionada" else "Imagen de la galería",
                    )
                }
            }
        } else {
            PanelAviso(
                R.drawable.figma_gallery,
                if (fotos == null) "Cargando galería…" else if (acceso) "No hay fotos disponibles" else "Acceso a tus fotos",
                if (acceso) "Elige una imagen con el selector de Android o toma una nueva foto."
                else "Puedes elegir una foto con Android aunque no concedas acceso a la galería.",
            )
        }
        if (elegida != null) androidx.compose.material3.TextButton(onClick = abrirSelector, enabled = !modelo.guardando) {
            Text("Abrir selector de Android")
        }
        if (!completo) androidx.compose.material3.TextButton(onClick = { pedirPermisos.launch(permisos) }, enabled = !modelo.guardando) {
            Text(if (parcial) "Elegir más fotos para la galería" else "Permitir galería")
        }
        modelo.mensaje?.let { Text(it, color = Danger) }
    }
}
