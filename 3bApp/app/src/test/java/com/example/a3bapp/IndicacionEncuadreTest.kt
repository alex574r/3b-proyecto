package com.example.a3bapp

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** Las indicaciones fijas de la cámara dicen cuándo acercarse y cuándo alejarse, tomando el marco como referencia. */
class IndicacionEncuadreTest {
    @Test fun textosAcordados() {
        assertEquals("Si el precio se ve pequeño, acércate. Si se corta el precio o la descripción, aléjate.",
            Evidencia.Etiqueta.indicaciones.joinToString(" "))
        assertEquals("Acércate hasta llenar el marco. Si se corta el empaque, aléjate.",
            Evidencia.Producto.indicaciones.joinToString(" "))
        assertEquals("Incluye la entrada y el letrero. Si el nombre queda fuera, aléjate.",
            Evidencia.Fachada.indicaciones.joinToString(" "))
    }

    @Test fun cadaEvidenciaIndicaCuandoAlejarseYEsCondicional() {
        Evidencia.entries.forEach { e ->
            val texto = e.indicaciones.joinToString(" ").lowercase()
            assertTrue(e.name, "aléjate" in texto)
            assertTrue(e.name, texto.startsWith("si ") || "si " in texto)
            assertTrue(e.name, e.indicaciones.size == 2 && e.indicaciones.all { it.length <= 60 })
        }
    }
}
