package com.example.a3bapp

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.example.a3bapp.ui.theme.Danger
import com.example.a3bapp.ui.theme.Line
import com.example.a3bapp.ui.theme.Muted
import com.example.a3bapp.ui.theme.Pending
import com.example.a3bapp.ui.theme.PendingBg
import com.example.a3bapp.ui.theme.PlexMono
import com.example.a3bapp.ui.theme.Success
import com.example.a3bapp.ui.theme.SuccessBg
import com.example.a3bapp.ui.theme.Wash
import org.json.JSONObject
import java.util.Locale
import kotlin.math.roundToInt

fun JSONObject.num(key: String): Double? =
    if (isNull(key)) null else optDouble(key).takeIf { it.isFinite() }

fun pesos(v: Double) = String.format(Locale.US, "$%.2f", v)

private val nombresValidaciones = mapOf(
    "tienda_fachada" to "Fachada",
    "producto" to "Producto",
    "codigo_barras" to "Código de barras",
    "evidencia_precio" to "Evidencia de precio",
)

@Composable
fun Identificador(texto: String, color: Color = Muted) {
    Text(texto, style = MaterialTheme.typography.bodySmall, fontFamily = PlexMono, color = color)
}

@Composable
private fun EstadoPildora(texto: String, tinta: Color, fondo: Color) {
    Surface(color = fondo, shape = RoundedCornerShape(40.dp)) {
        Text(texto, color = tinta, style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(horizontal = 9.dp, vertical = 4.dp))
    }
}

@Composable
fun ResultadoCard(r: JSONObject) {
    val decision = r.str("decision_esperada").ifEmpty { r.str("decision") }
    val (titulo, estado, color) = when (decision) {
        "aprobada" -> Triple("Evidencia aprobada", "✓ Aprobada", Success)
        "rechazada" -> Triple("Captura rechazada", "× Rechazada", Danger)
        else -> Triple("En revisión manual", "◷ Revisión manual", Pending)
    }
    val fondo = when (color) {
        Success -> SuccessBg
        Danger -> Wash
        else -> PendingBg
    }
    val motivo = r.str("motivo_rechazo").ifBlank { r.str("titulo") }.ifBlank {
        r.str("reason_code").lowercase(Locale.ROOT).replace('_', ' ').replaceFirstChar { it.titlecase(Locale.ROOT) }
    }
    Titular("Dictamen del motor", titulo, motivo.takeIf(String::isNotBlank))
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
        Identificador(r.str("capture_id"))
        EstadoPildora(estado, color, fondo)
    }
    Panel {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Text("Confianza del motor", style = MaterialTheme.typography.titleSmall)
            val confianza = r.num("confidence_score")?.let { "${(it.coerceIn(0.0, 1.0) * 100).roundToInt()} %" } ?: "—"
            Text(confianza, color = color, style = MaterialTheme.typography.headlineSmall)
        }
        Identificador(r.str("reason_code"), color)
    }
    r.optJSONObject("validaciones")?.let { validaciones ->
        Panel {
            Text("Validaciones", style = MaterialTheme.typography.titleMedium)
            validaciones.keys().asSequence().sortedBy { nombresValidaciones.keys.indexOf(it).let { i -> if (i < 0) Int.MAX_VALUE else i } }
                .forEach { clave ->
                    val estadoCampo = validaciones.str(clave)
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(nombresValidaciones[clave] ?: clave, Modifier.weight(1f), style = MaterialTheme.typography.titleSmall)
                        when (estadoCampo) {
                            "ok" -> EstadoPildora("✓ OK", Success, SuccessBg)
                            "falla" -> EstadoPildora("× Falla", Danger, Wash)
                            "no_evaluable" -> EstadoPildora("— No evaluable", Muted, Wash)
                            else -> EstadoPildora(estadoCampo, Muted, Wash)
                        }
                    }
                }
        }
    }
    Panel {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
            androidx.compose.foundation.layout.Column(Modifier.weight(1f)) {
                Text("PRECIO DETECTADO", style = MaterialTheme.typography.labelSmall, color = Muted)
                Text(r.num("precio_detectado")?.let(::pesos) ?: "—", style = MaterialTheme.typography.headlineSmall)
            }
            androidx.compose.foundation.layout.Column(Modifier.weight(1f)) {
                Text("CÓDIGO DETECTADO", style = MaterialTheme.typography.labelSmall, color = Muted)
                Identificador(r.str("codigo_barras_detectado").ifBlank { "—" })
            }
        }
        r.num("precio_descuento")?.let {
            Text("Precio de oferta: ${pesos(it)}", color = Success, fontWeight = FontWeight.Bold)
        }
        r.num("id_product")?.let { sku ->
            HorizontalDivider(color = Line)
            val ref = r.num("product_price")
            val min = r.num("min_product_price")
            val max = r.num("max_product_price")
            Text("SKU ${sku.toLong()}" + (ref?.let { " · Referencia ${pesos(it)}" } ?: "") +
                (if (min != null && max != null) " (rango ${pesos(min)}–${pesos(max)})" else ""),
                style = MaterialTheme.typography.bodySmall)
            listOf(r.str("product_group"), r.str("product_line")).filter(String::isNotBlank).takeIf { it.isNotEmpty() }?.let {
                Text(it.joinToString(" · "), style = MaterialTheme.typography.bodySmall)
            }
        }
    }
    r.str("explicacion").takeIf(String::isNotBlank)?.let { Text(it, color = Muted) }
}

@Composable
fun RespuestaJson(json: String) {
    Panel {
        Text("JSON de respuesta", style = MaterialTheme.typography.titleSmall)
        SelectionContainer { Identificador(json) }
    }
}

@Composable
fun PantallaProcesando(volver: () -> Unit, id: String?, progreso: Float? = null) {
    EncabezadoCaptura("Procesamiento", volver) {
        Titular("Procesamiento", "Analizando captura", "Estamos verificando la fachada, el producto, el código y el precio.")
        Panel {
            Text("Verificando evidencia…", style = MaterialTheme.typography.titleMedium)
            if (progreso == null) LinearProgressIndicator(Modifier.fillMaxWidth())
            else {
                LinearProgressIndicator(progress = { progreso }, modifier = Modifier.fillMaxWidth())
                Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.CenterEnd) {
                    Identificador("${(progreso * 100).roundToInt()} %")
                }
            }
            id?.let { Identificador(it) }
        }
    }
}
