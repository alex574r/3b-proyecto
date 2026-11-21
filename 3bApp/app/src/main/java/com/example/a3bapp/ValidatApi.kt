package com.example.a3bapp

import android.content.ContentResolver
import android.graphics.Bitmap
import android.graphics.ImageDecoder
import android.net.Uri
import android.util.Base64
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL

/** Cliente de la API del motor (validat3b/server.py). Bloqueante: llamar desde Dispatchers.IO. */
object ValidatApi {
    /** JPEG reducido a maxSide px; ImageDecoder aplica la orientación EXIF (el servidor ya no la ve tras recomprimir). */
    fun jpeg(cr: ContentResolver, uri: Uri, maxSide: Int = 1280): ByteArray {
        val bmp = ImageDecoder.decodeBitmap(ImageDecoder.createSource(cr, uri)) { dec, info, _ ->
            val s = maxSide.toFloat() / maxOf(info.size.width, info.size.height)
            if (s < 1f) dec.setTargetSize((info.size.width * s).toInt(), (info.size.height * s).toInt())
            dec.allocator = ImageDecoder.ALLOCATOR_SOFTWARE
        }
        return ByteArrayOutputStream().also { bmp.compress(Bitmap.CompressFormat.JPEG, 85, it) }.toByteArray()
    }

    /** fields: campos de la captura; photos: facade/product/shelf en JPEG. Devuelve el JSON oficial. */
    fun validar(baseUrl: String, token: String, fields: JSONObject, photos: Map<String, ByteArray>): JSONObject {
        val body = JSONObject(fields.toString())
        photos.forEach { (k, v) -> body.put("${k}_b64", Base64.encodeToString(v, Base64.NO_WRAP)) }
        val conn = (URL(baseUrl.trimEnd('/') + "/validar").openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            doOutput = true
            connectTimeout = 10_000
            readTimeout = 90_000 // el servidor espera a Haiku
            setRequestProperty("Content-Type", "application/json; charset=utf-8")
            if (token.isNotBlank()) setRequestProperty("X-Api-Key", token)
        }
        try {
            conn.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            val ok = conn.responseCode in 200..299
            val text = (if (ok) conn.inputStream else conn.errorStream)
                ?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            if (!ok) error("HTTP ${conn.responseCode}: $text")
            return JSONObject(text)
        } finally {
            conn.disconnect()
        }
    }
}
