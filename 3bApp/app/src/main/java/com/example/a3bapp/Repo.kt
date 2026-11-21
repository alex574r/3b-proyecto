package com.example.a3bapp

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.Uri
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import org.json.JSONException
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.util.concurrent.TimeUnit

fun JSONObject.str(key: String) = if (isNull(key)) "" else optString(key)

/** true = vale la pena reintentar: sin red, timeout, 408/429/5xx o una respuesta que no es JSON (p. ej. portal cautivo). */
fun esTransitorio(e: Throwable): Boolean = when (e) {
    is HttpError -> e.code == 408 || e.code == 429 || e.code >= 500
    is IOException, is JSONException -> true
    else -> false
}

/** Campos que el usuario dejó escritos al guardar la captura; los vacíos no se mandan. */
fun Captura.campos(): JSONObject = JSONObject().also { j ->
    mapOf(
        "capture_store_name" to tienda, "capture_barcode" to barcode, "capture_price" to precio, "capture_brand" to marca,
        "product_name" to nombre, "unit_quantity_product" to contenido, "unit_product" to unidad,
    ).forEach { (k, v) -> if (v.isNotBlank()) j.put(k, v.trim()) }
}

/**
 * Offline-first: cada análisis se guarda primero en Room (con sus fotos) y después se intenta enviar. Si no hay red o es mala,
 * queda PENDIENTE y WorkManager lo reenvía cuando vuelve la conexión.
 * Los envíos corren en un alcance propio de la app, así que sobreviven a cambiar de pantalla.
 */
object CapturaRepo {
    const val MAX_INTENTOS = 8
    private val mutex = Mutex() // un solo envío a la vez: evita analizar dos veces la misma captura (cada análisis gasta tokens)
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    val enProceso = MutableStateFlow<Set<Long>>(emptySet())

    private fun dao(ctx: Context) = AppDb.get(ctx).dao()
    fun observar(ctx: Context, id: Long) = dao(ctx).observar(id)
    fun observarTodas(ctx: Context) = dao(ctx).observarTodas()
    fun contarPendientes(ctx: Context) = dao(ctx).contarPendientes()
    suspend fun hayPendientes(ctx: Context) = dao(ctx).idsPendientes().isNotEmpty()

    private fun prefs(ctx: Context) = ctx.getSharedPreferences("config", Context.MODE_PRIVATE)
    fun apiUrl(ctx: Context): String = prefs(ctx).getString("api_url", null) ?: BuildConfig.API_URL

    /** Solo para builds debug (MainActivity): apunta a un servidor local. null vuelve a la URL de producción. */
    fun setApiUrl(ctx: Context, url: String?) =
        prefs(ctx).edit().also { if (url == null) it.remove("api_url") else it.putString("api_url", url) }.apply()

    fun enLinea(ctx: Context): Boolean {
        val cm = ctx.getSystemService(ConnectivityManager::class.java)
        val caps = cm.getNetworkCapabilities(cm.activeNetwork) ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) &&
            caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
    }

    /** Reduce y guarda las 3 fotos en filesDir y crea la fila PENDIENTE. No se cancela aunque el usuario cambie de pantalla. */
    suspend fun nueva(ctx: Context, campos: Map<String, String>, fotos: List<Uri>): Long =
        withContext(NonCancellable + Dispatchers.IO) {
            val dir = File(ctx.filesDir, "capturas").apply { mkdirs() }
            val ahora = System.currentTimeMillis()
            val rutas = listOf("fachada", "producto", "etiqueta").mapIndexed { i, n ->
                File(dir, "${ahora}_$n.jpg").also { it.writeBytes(ValidatApi.jpeg(ctx.contentResolver, fotos[i])) }.path
            }
            fun campo(k: String) = campos[k].orEmpty().trim()
            val id = dao(ctx).insertar(
                Captura(
                    creadaEn = ahora, estado = Estado.PENDIENTE, fachada = rutas[0], producto = rutas[1], etiqueta = rutas[2],
                    tienda = campo("capture_store_name"), barcode = campo("capture_barcode"), precio = campo("capture_price"),
                    marca = campo("capture_brand"), nombre = campo("product_name"),
                    contenido = campo("unit_quantity_product"), unidad = campo("unit_product"),
                ),
            )
            programarSync(ctx, nueva = true)
            id
        }

    /**
     * Intenta enviar una captura y devuelve su estado final. manual = el usuario pulsó "Reintentar": también reintenta las que
     * quedaron en ERROR y reinicia el conteo de intentos.
     */
    suspend fun enviar(ctx: Context, id: Long, manual: Boolean = false): String {
        enProceso.update { it + id }
        try {
            return mutex.withLock { intentar(ctx, id, manual) }
        } finally {
            enProceso.update { it - id }
        }
    }

    private suspend fun intentar(ctx: Context, id: Long, manual: Boolean): String = withContext(Dispatchers.IO) {
        val dao = dao(ctx)
        val c = dao.get(id) ?: return@withContext Estado.ERROR
        if (c.estado == Estado.ENVIADA || (c.estado == Estado.ERROR && !manual)) return@withContext c.estado
        val previos = if (manual) 0 else c.intentos
        if (!enLinea(ctx)) { // sin red no se gasta un intento ni se espera a un timeout
            dao.actualizar(c.copy(estado = Estado.PENDIENTE, error = "Sin conexión"))
            programarSync(ctx)
            return@withContext Estado.PENDIENTE
        }
        try {
            val fotos = mapOf(
                "facade" to File(c.fachada).readBytes(), "product" to File(c.producto).readBytes(),
                "shelf" to File(c.etiqueta).readBytes(),
            )
            // La respuesta es un registro con la forma de capturas.json (+ detalle del motor al final)
            val r = JSONObject(ValidatApi.analizar(apiUrl(ctx), c.campos(), fotos))
            dao.actualizar(
                c.copy(
                    estado = Estado.ENVIADA, intentos = previos + 1, error = null,
                    tienda = r.str("capture_store_name"), barcode = r.str("capture_barcode"), precio = r.str("capture_price"),
                    marca = r.str("capture_brand"), nombre = r.str("product_name"),
                    contenido = r.str("unit_quantity_product"), unidad = r.str("unit_product"),
                    // motivo para la lista del historial: el texto del analista si se rechazó, si no el código del motor
                    decision = r.getString("decision_esperada"), motivo = r.str("motivo_rechazo").ifBlank { r.getString("reason_code") },
                    resultadoJson = r.toString(2).replace("\\/", "/"), // org.json escapa "/"; el JSON sigue siendo válido
                ),
            )
            Estado.ENVIADA
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            val n = previos + 1
            val msg = e.message?.take(200) ?: e::class.java.simpleName
            if (esTransitorio(e) && n < MAX_INTENTOS) {
                dao.actualizar(c.copy(estado = Estado.PENDIENTE, intentos = n, error = msg))
                programarSync(ctx)
                Estado.PENDIENTE
            } else {
                val motivo = if (esTransitorio(e)) "Sin respuesta tras $n intentos: $msg" else msg
                dao.actualizar(c.copy(estado = Estado.ERROR, intentos = n, error = motivo))
                Estado.ERROR
            }
        }
    }

    fun enviarYa(ctx: Context, id: Long, manual: Boolean = false) {
        val app = ctx.applicationContext
        enProceso.update { it + id } // la pantalla muestra "enviando" de inmediato
        scope.launch { enviar(app, id, manual) }
    }

    /** Envía todas las PENDIENTES en orden. true si ninguna quedó pendiente. */
    suspend fun sincronizar(ctx: Context, manual: Boolean = false): Boolean {
        var todoBien = true
        for (id in dao(ctx).idsPendientes()) if (enviar(ctx, id, manual) == Estado.PENDIENTE) todoBien = false
        return todoBien
    }

    fun sincronizarYa(ctx: Context) {
        val app = ctx.applicationContext
        scope.launch { sincronizar(app, manual = true) }
    }

    /** Un solo trabajo en cola: espera red y reintenta con espera creciente (30 s, 60 s, 2 min...). */
    fun programarSync(ctx: Context, nueva: Boolean = false) {
        val req = OneTimeWorkRequestBuilder<SyncWorker>()
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .setInitialDelay(if (nueva) 0L else 30L, TimeUnit.SECONDS)
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
            .build()
        val politica = if (nueva) ExistingWorkPolicy.APPEND_OR_REPLACE else ExistingWorkPolicy.KEEP
        WorkManager.getInstance(ctx.applicationContext).enqueueUniqueWork("sync-capturas", politica, req)
    }

    /** Al abrir la app: si quedaron pendientes de una sesión anterior, vuelve a programar su envío. */
    fun retomarPendientes(ctx: Context) {
        val app = ctx.applicationContext
        scope.launch { if (hayPendientes(app)) programarSync(app) }
    }

    fun borrarYa(ctx: Context, id: Long) {
        val app = ctx.applicationContext
        scope.launch {
            mutex.withLock { // espera a que termine un envío en curso antes de borrar sus fotos
                dao(app).get(id)?.let { c ->
                    listOf(c.fachada, c.producto, c.etiqueta).forEach { File(it).delete() }
                    dao(app).borrar(c)
                }
            }
        }
    }
}

class SyncWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {
    override suspend fun doWork(): Result {
        val ok = CapturaRepo.sincronizar(applicationContext)
        // si mientras tanto llegó otra pendiente, se vuelve a correr
        return if (ok && !CapturaRepo.hayPendientes(applicationContext)) Result.success() else Result.retry()
    }
}
