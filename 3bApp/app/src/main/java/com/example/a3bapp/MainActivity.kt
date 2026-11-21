package com.example.a3bapp

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.saveable.rememberSaveableStateHolder
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.example.a3bapp.ui.theme.Paper
import com.example.a3bapp.ui.theme._3bAppTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.light(0, 0),
            navigationBarStyle = SystemBarStyle.light(0, 0),
        )
        CapturaRepo.retomarPendientes(this)
        setContent { _3bAppTheme { App() } }
    }
}

@Composable
fun App(modelo: CapturaUiModel = viewModel()) {
    val ctx = LocalContext.current
    var historial by rememberSaveable { mutableStateOf(false) }
    val estadoHistorial = rememberSaveableStateHolder()
    val pendientes by CapturaRepo.contarPendientes(ctx).collectAsStateWithLifecycle(0)
    BackHandler(enabled = historial) { historial = false }
    Scaffold(
        modifier = Modifier.fillMaxSize(),
        bottomBar = {
            if (historial || modelo.pantalla == Pantalla.Inicio) {
                NavigationBar(containerColor = Paper) {
                    NavigationBarItem(
                        selected = !historial, onClick = { historial = false },
                        icon = { Icono(R.drawable.figma_camera) }, label = { Text("Captura") },
                    )
                    NavigationBarItem(
                        selected = historial, onClick = { historial = true },
                        icon = {
                            BadgedBox(badge = { if (pendientes > 0) Badge { Text("$pendientes") } }) {
                                Icono(R.drawable.figma_inbox)
                            }
                        },
                        label = { Text("Historial") },
                    )
                }
            }
        },
    ) { padding ->
        if (historial) {
            estadoHistorial.SaveableStateProvider("historial") { HistorialScreen(Modifier.padding(padding)) }
        } else {
            CapturaFlujo(modelo, Modifier.padding(padding))
        }
    }
}
