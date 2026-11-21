package com.example.a3bapp

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PrecioCapturaTest {
    @Test fun aceptaPrecioOpcionalOMxnNoNegativo() {
        listOf("", "  ", "0", "42", "42.50", "42,50", " 42,50 ", ".50").forEach {
            assertTrue(it, precioValido(it))
        }
    }

    @Test fun rechazaImportesInvalidos() {
        listOf("-1", "abc", "NaN", "Infinity", "5.2.1", "1,234.56", "1e2", "1".repeat(400)).forEach {
            assertFalse(it, precioValido(it))
        }
    }
}
