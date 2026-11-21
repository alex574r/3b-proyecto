package com.example.a3bapp

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import java.io.File

class CamaraGuiada : ComponentActivity() {
    private val permiso = registerForActivityResult(ActivityResultContracts.RequestPermission()) {
        if (it) mostrarCamara() else {
            android.widget.Toast.makeText(this, "Activa el permiso de cámara o elige una foto de la galería.", android.widget.Toast.LENGTH_LONG).show()
            finish()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) mostrarCamara()
        else permiso.launch(Manifest.permission.CAMERA)
    }

    private fun mostrarCamara() {
        val tipo = intent.getStringExtra("tipo") ?: "Etiqueta"
        val indicacion = when (tipo) {
            "Producto" -> "Acércate hasta llenar el marco con el producto. Incluye la marca y el contenido."
            "Fachada" -> "Encuadra la entrada y el letrero de la tienda."
            else -> "Acércate hasta que el precio y la descripción quepan juntos dentro del marco."
        }
        val executor = ContextCompat.getMainExecutor(this)
        val capturar = ImageCapture.Builder().setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY).build()
        setContent {
            var lista by remember { mutableStateOf(false) }
            var tomando by remember { mutableStateOf(false) }
            var error by remember { mutableStateOf<String?>(null) }
            Column(Modifier.fillMaxSize().background(Color.Black).safeDrawingPadding()) {
                Text(error ?: indicacion, Modifier.padding(16.dp), color = Color.White)
                Box(Modifier.fillMaxWidth().weight(1f), contentAlignment = Alignment.Center) {
                    AndroidView(factory = { ctx ->
                        PreviewView(ctx).apply {
                            implementationMode = PreviewView.ImplementationMode.COMPATIBLE
                            scaleType = PreviewView.ScaleType.FILL_CENTER
                            val provider = ProcessCameraProvider.getInstance(ctx)
                            provider.addListener({
                                if (!isFinishing && !isDestroyed) {
                                    try {
                                        val preview = Preview.Builder().build()
                                        preview.setSurfaceProvider(surfaceProvider)
                                        provider.get().bindToLifecycle(this@CamaraGuiada, CameraSelector.DEFAULT_BACK_CAMERA, preview, capturar)
                                        lista = true
                                    } catch (e: Exception) {
                                        android.util.Log.w("CamaraGuiada", "Error al abrir la cámara", e)
                                        error = "Cámara no disponible. Vuelve y elige una foto de la galería."
                                    }
                                }
                            }, executor)
                        }
                    }, modifier = Modifier.fillMaxSize())
                    Box(Modifier.fillMaxWidth(if (tipo == "Producto") .62f else .84f)
                        .fillMaxHeight(when (tipo) { "Producto" -> .64f; "Fachada" -> .45f; else -> .27f })
                        .border(3.dp, Color.White, RoundedCornerShape(12.dp)))
                }
                Text("Mantén el teléfono quieto al tomar la foto.", Modifier.padding(horizontal = 16.dp), color = Color.White)
                Row(Modifier.fillMaxWidth().padding(12.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                    TextButton(onClick = { finish() }) { Text("Volver", color = Color.White) }
                    Button(enabled = lista && !tomando, onClick = {
                        tomando = true
                        val file = File.createTempFile("foto_", ".jpg", File(cacheDir, "photos").apply { mkdirs() })
                        capturar.takePicture(ImageCapture.OutputFileOptions.Builder(file).build(), executor,
                            object : ImageCapture.OnImageSavedCallback {
                                override fun onImageSaved(result: ImageCapture.OutputFileResults) {
                                    val uri = FileProvider.getUriForFile(this@CamaraGuiada, "${packageName}.fileprovider", file)
                                    setResult(RESULT_OK, Intent().setData(uri))
                                    finish()
                                }
                                override fun onError(exc: ImageCaptureException) {
                                    file.delete()
                                    tomando = false
                                    error = "No se pudo guardar. Intenta tomar la foto otra vez."
                                }
                            })
                    }) { Text("Tomar foto") }
                }
            }
        }
    }
}


