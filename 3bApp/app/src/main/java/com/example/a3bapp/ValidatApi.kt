package com.example.a3bapp

import android.content.ContentResolver
import android.graphics.Bitmap
import android.graphics.ImageDecoder
import android.net.Uri
import android.util.Base64
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/** El servidor respondió con un código distinto de 2xx. */
class HttpError(val code: Int, val body: String) : Exception("HTTP $code: ${body.take(200)}")

/** Cliente de la API del motor (validat3b/server.py). Bloqueante: llamar desde Dispatchers.IO. */
object ValidatApi {
    private const val TOPE_MS = 100_000L // Cloudflare corta a los 100 s

    /** ImageDecoder aplica la orientación EXIF (el servidor ya no la ve tras recomprimir). */
    private fun reducir(src: ImageDecoder.Source, maxSide: Int): Bitmap =
        ImageDecoder.decodeBitmap(src) { dec, info, _ ->
            val s = maxSide.toFloat() / maxOf(info.size.width, info.size.height)
            if (s < 1f) dec.setTargetSize((info.size.width * s).toInt(), (info.size.height * s).toInt())
            dec.allocator = ImageDecoder.ALLOCATOR_SOFTWARE
        }

    /** JPEG reducido a maxSide px para subirlo. */
    fun jpeg(cr: ContentResolver, uri: Uri, maxSide: Int = 1280): ByteArray =
        ByteArrayOutputStream().also {
            reducir(ImageDecoder.createSource(cr, uri), maxSide).compress(Bitmap.CompressFormat.JPEG, 85, it)
        }.toByteArray()

    /** Miniatura para mostrar en pantalla. */
    fun thumb(cr: ContentResolver, uri: Uri): Bitmap = reducir(ImageDecoder.createSource(cr, uri), 480)

    fun thumbFile(path: String): Bitmap = reducir(ImageDecoder.createSource(File(path)), 480)

    /** JWT HS256 de vida corta firmado con el secreto compartido con el servidor (VALIDAT3B_JWT_SECRET). */
    fun jwt(secret: String, ttlSec: Long = 300): String {
        fun b64(b: ByteArray) = Base64.encodeToString(b, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
        val now = System.currentTimeMillis() / 1000
        val head = b64("""{"alg":"HS256","typ":"JWT"}""".toByteArray())
        val body = b64("""{"iss":"3bApp","iat":$now,"exp":${now + ttlSec}}""".toByteArray())
        val mac = Mac.getInstance("HmacSHA256").apply { init(SecretKeySpec(secret.toByteArray(), "HmacSHA256")) }
        return "$head.$body.${b64(mac.doFinal("$head.$body".toByteArray()))}"
    }

    private fun post(baseUrl: String, path: String, fields: JSONObject, photos: Map<String, ByteArray>, headers: Map<String, String>): String {
        val body = JSONObject(fields.toString())
        photos.forEach { (k, v) -> body.put("${k}_b64", Base64.encodeToString(v, Base64.NO_WRAP)) }
        val conn = (URL(baseUrl.trimEnd('/') + path).openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            doOutput = true
            connectTimeout = 8_000
            readTimeout = 90_000 // el servidor espera a Haiku
            setRequestProperty("Content-Type", "application/json; charset=utf-8")
            headers.forEach { (k, v) -> setRequestProperty(k, v) }
        }
        // Con mala señal la subida puede quedarse colgada sin que salte ningún timeout: tope total que corta el socket.
        val watchdog = Thread { try { Thread.sleep(TOPE_MS); conn.disconnect() } catch (_: InterruptedException) {} }
            .apply { isDaemon = true; start() }
        try {
            conn.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            val ok = conn.responseCode in 200..299
            val text = (if (ok) conn.inputStream else conn.errorStream)
                ?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            if (!ok) throw HttpError(conn.responseCode, text)
            return text
        } finally {
            watchdog.interrupt()
            conn.disconnect()
        }
    }

    /** /validar con los campos de la captura y token fijo opcional (X-Api-Key). Devuelve el JSON oficial tal cual. */
    fun validar(baseUrl: String, token: String, fields: JSONObject, photos: Map<String, ByteArray>): String =
        post(baseUrl, "/validar", fields, photos, if (token.isBlank()) emptyMap() else mapOf("X-Api-Key" to token))

    /** /analizar: solo fotos (fields opcional). Devuelve {"resultado": JSON oficial, "datos_detectados": {...}}. */
    fun analizar(baseUrl: String, fields: JSONObject, photos: Map<String, ByteArray>): String =
        post(
            baseUrl, "/analizar", fields, photos,
            if (BuildConfig.JWT_SECRET.isBlank()) emptyMap() else mapOf("Authorization" to "Bearer ${jwt(BuildConfig.JWT_SECRET)}"),
        )
}
