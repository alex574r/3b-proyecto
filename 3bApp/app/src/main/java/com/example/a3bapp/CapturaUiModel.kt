package com.example.a3bapp

import android.app.Application
import android.net.Uri
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.io.IOException

enum class Pantalla { Inicio, Guia, Camara, Galeria, VistaPrevia, Revision, Analisis, Demo, DemoAnalisis, DemoResultado, DemoRevision, DemoRed }

enum class Evidencia(
    val titulo: String,
    val instruccion: String,
    val objetivo: String,
    val cuidado: String,
    val ejemplo: String,
) {
    Fachada("Fachada", "Incluye el nombre o logotipo de la tienda y el acceso principal.", "Nombre o logo de la tienda", "Evita que el acceso o el rótulo queden cortados.", "fachada.png"),
    Producto("Producto", "Acércate hasta que el empaque llene el encuadre. Evita fotos de pantalla.", "Frente del empaque", "Mantén el nombre y la presentación visibles.", "producto.png"),
    Etiqueta("Etiqueta", "Acércate hasta que el precio y la descripción quepan juntos en el marco.", "Precio + descripción", "Evita reflejos. Revisa que se vea el precio unitario.", "etiqueta.png"),
}

enum class CampoCaptura(val clave: String, val titulo: String) {
    Precio("capture_price", "Precio (MXN)"), Codigo("capture_barcode", "Código de barras"),
    Producto("product_name", "Producto"), Marca("capture_brand", "Marca"),
    Cantidad("unit_quantity_product", "Cantidad"), Unidad("unit_product", "Unidad"),
    Tienda("capture_store_name", "Tienda / cadena"),
}

private val importe = Regex("""(?:[0-9]+(?:[.,][0-9]*)?|[.,][0-9]+)""")

internal fun precioValido(valor: String): Boolean {
    val texto = valor.trim()
    return texto.isEmpty() || (importe.matches(texto) && texto.replace(',', '.').toDoubleOrNull()?.isFinite() == true)
}

class CapturaUiModel(application: Application, private val estado: SavedStateHandle) : AndroidViewModel(application) {
    private val ctx = application
    private val borradores get() = File(ctx.cacheDir, "guia-captura")
    private val fotosIniciales = List(Evidencia.entries.size) { "" }
    private val camposIniciales = List(CampoCaptura.entries.size) { "" }

    var pantalla by mutableStateOf(estado.get<String>("pantalla")?.let(Pantalla::valueOf) ?: Pantalla.Inicio)
        private set
    private var retomable by mutableStateOf(estado.get<String>("retomable")?.let(Pantalla::valueOf))
    var fotos by mutableStateOf<List<String>>(estado.get<ArrayList<String>>("fotos") ?: fotosIniciales)
        private set
    var campos by mutableStateOf<List<String>>(estado.get<ArrayList<String>>("campos") ?: camposIniciales)
        private set
    var evidencia by mutableStateOf(Evidencia.entries[estado.get<Int>("evidencia") ?: 0])
        private set
    var reemplazo by mutableStateOf(estado.get<Boolean>("reemplazo") ?: false)
        private set
    var candidata by mutableStateOf(estado.get<String>("candidata"))
        private set
    var id by mutableStateOf(estado.get<Long>("id"))
        private set
    var precioInvalido by mutableStateOf(estado.get<Boolean>("precioInvalido") ?: false)
        private set
    var simulacion by mutableStateOf(estado.get<String>("simulacion").orEmpty())
        private set
    var guardando by mutableStateOf(false)
        private set
    var mensaje by mutableStateOf<String?>(null)
        private set

    val enProceso = CapturaRepo.enProceso
    val puedeContinuar get() = retomable != null
    val fotosListas get() = fotos.count { it.isNotEmpty() }
    fun observar(capturaId: Long?) = capturaId?.let { CapturaRepo.observar(ctx, it) } ?: flowOf(null)

    fun ir(destino: Pantalla) {
        pantalla = destino
        estado["pantalla"] = destino.name
        mensaje = null
    }

    fun inicio() {
        if (guardando) return
        retomable = pantalla
        estado["retomable"] = pantalla.name
        ir(Pantalla.Inicio)
    }

    fun continuar() = ir(retomable ?: Pantalla.Guia)

    fun nueva() {
        if (guardando) return
        limpiarBorrador()
        abrirEvidencia(Evidencia.Fachada, false)
    }

    private fun limpiarBorrador() {
        fotos.filter { it.isNotEmpty() }.forEach { File(it).delete() }
        descartarCandidata()
        fotos = fotosIniciales
        campos = camposIniciales
        estado["fotos"] = ArrayList(fotos)
        estado["campos"] = ArrayList(campos)
        id = null
        estado.remove<Long>("id")
        precioInvalido = false
        estado["precioInvalido"] = false
        estado.remove<Long>("autollenadoId")
        estado.remove<ArrayList<String>>("camposEnviados")
        estado.remove<ArrayList<String>>("fotosEnviadas")
        retomable = null
        estado.remove<String>("retomable")
        evidencia = Evidencia.Fachada
        estado["evidencia"] = evidencia.ordinal
        reemplazo = false
        estado["reemplazo"] = false
    }

    fun abrirEvidencia(tipo: Evidencia, editar: Boolean) {
        evidencia = tipo
        estado["evidencia"] = tipo.ordinal
        reemplazo = editar
        estado["reemplazo"] = editar
        ir(if (editar) Pantalla.Camara else Pantalla.Guia)
    }

    fun nuevaFoto(): File = File.createTempFile("foto-", ".jpg", borradores.apply { mkdirs() })

    fun importar(uri: Uri) {
        if (guardando) return
        guardando = true
        viewModelScope.launch {
            try {
                val archivo = withContext(Dispatchers.IO) {
                    nuevaFoto().also { destino ->
                        try {
                            destino.writeBytes(ValidatApi.jpeg(ctx.contentResolver, uri))
                        } catch (e: Exception) {
                            destino.delete()
                            throw e
                        }
                    }
                }
                revisarFoto(archivo)
            } catch (e: CancellationException) {
                throw e
            } catch (_: Exception) {
                mensaje = "No se pudo abrir la foto. Elige otra imagen."
            } finally {
                guardando = false
            }
        }
    }

    fun revisarFoto(archivo: File) {
        if (pantalla != Pantalla.Camara && pantalla != Pantalla.Galeria) {
            archivo.delete()
            return
        }
        descartarCandidata()
        candidata = archivo.path
        estado["candidata"] = archivo.path
        if (reemplazo) ir(Pantalla.VistaPrevia) else aceptarFoto()
    }

    fun descartarCandidata() {
        candidata?.let { File(it).delete() }
        candidata = null
        estado.remove<String>("candidata")
    }

    fun aceptarFoto() {
        val archivo = candidata?.takeIf { File(it).isFile } ?: return
        fotos[evidencia.ordinal].takeIf { it.isNotEmpty() }?.let { File(it).delete() }
        fotos = fotos.toMutableList().apply { set(evidencia.ordinal, archivo) }
        estado["fotos"] = ArrayList(fotos)
        candidata = null
        estado.remove<String>("candidata")
        if (reemplazo || evidencia == Evidencia.Etiqueta) ir(Pantalla.Revision)
        else abrirEvidencia(Evidencia.entries[evidencia.ordinal + 1], false)
    }

    fun campo(campo: CampoCaptura, valor: String) {
        campos = campos.toMutableList().apply { set(campo.ordinal, valor) }
        estado["campos"] = ArrayList(campos)
        if (campo == CampoCaptura.Precio && precioValido(valor)) {
            precioInvalido = false
            estado["precioInvalido"] = false
        }
    }

    fun autollenar(captura: Captura) {
        if (captura.id != id || estado.get<Long>("autollenadoId") == captura.id) return
        estado["autollenadoId"] = captura.id
        val enviados = estado.get<ArrayList<String>>("camposEnviados") ?: return
        val detectados = listOf(captura.precio, captura.barcode, captura.nombre, captura.marca, captura.contenido, captura.unidad, captura.tienda)
        campos = campos.mapIndexed { indice, valor -> if (valor == enviados[indice]) detectados[indice] else valor }
        estado["campos"] = ArrayList(campos)
    }

    fun analizar(anterior: Captura?) {
        if (guardando) return
        precioInvalido = !precioValido(campos[CampoCaptura.Precio.ordinal])
        estado["precioInvalido"] = precioInvalido
        if (precioInvalido) return
        if (fotos.any { it.isBlank() || !File(it).isFile }) {
            mensaje = "Falta una foto. Vuelve a seleccionarla antes de analizar."
            return
        }
        val importeNormalizado = campos[CampoCaptura.Precio.ordinal].trim().replace(',', '.')
        val datos = CampoCaptura.entries.associate { campo ->
            campo.clave to (if (campo == CampoCaptura.Precio) importeNormalizado else campos[campo.ordinal])
        }
        if (anterior != null && anterior.estado != Estado.ENVIADA && fotos == estado.get<ArrayList<String>>("fotosEnviadas") &&
            CampoCaptura.entries.all { anterior.campos().str(it.clave) == datos.getValue(it.clave).trim() }) {
            reintentar(anterior.id)
            return
        }
        val archivos = fotos.toList()
        guardando = true
        viewModelScope.launch {
            try {
                CapturaRepo.nueva(ctx, datos, archivos.map { Uri.fromFile(File(it)) })
                limpiarBorrador()
                ir(Pantalla.Inicio)
                mensaje = "Captura guardada. Puedes comenzar la siguiente o consultar el historial."
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                ir(Pantalla.Revision)
                mensaje = if (e is IOException) "No se pudieron guardar las fotos. Vuelve a intentarlo."
                else "No se pudo guardar la captura. Vuelve a intentarlo."
            } finally {
                guardando = false
            }
        }
    }

    fun reintentar(capturaId: Long) {
        if (capturaId in enProceso.value) return
        ir(Pantalla.Analisis)
        CapturaRepo.enviarYa(ctx, capturaId, manual = true)
    }

    fun simular(destino: Pantalla, caso: String = "") {
        simulacion = caso
        estado["simulacion"] = caso
        ir(destino)
    }

    fun volver() {
        if (guardando) return
        when (pantalla) {
            Pantalla.Inicio -> Unit
            Pantalla.Guia -> {
                if (evidencia == Evidencia.Fachada) inicio()
                else abrirEvidencia(Evidencia.entries[evidencia.ordinal - 1], false)
            }
            Pantalla.Camara, Pantalla.Galeria -> ir(if (reemplazo) Pantalla.Revision else Pantalla.Guia)
            Pantalla.VistaPrevia -> {
                descartarCandidata()
                ir(if (reemplazo) Pantalla.Revision else Pantalla.Guia)
            }
            Pantalla.Revision -> abrirEvidencia(Evidencia.Etiqueta, false)
            Pantalla.Analisis -> inicio()
            Pantalla.Demo -> ir(Pantalla.Inicio)
            Pantalla.DemoAnalisis, Pantalla.DemoResultado, Pantalla.DemoRevision, Pantalla.DemoRed -> ir(Pantalla.Demo)
        }
    }
}
