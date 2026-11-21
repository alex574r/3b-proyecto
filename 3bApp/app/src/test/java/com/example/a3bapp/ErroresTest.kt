package com.example.a3bapp

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.IOException
import java.net.ConnectException
import java.net.SocketTimeoutException
import java.net.UnknownHostException

/** Qué fallos dejan la captura PENDIENTE (se reintenta) y cuáles la pasan a ERROR (no se reintenta sola). */
class ErroresTest {
    @Test fun sinRedOMalaSenalSeReintenta() {
        listOf(IOException(), UnknownHostException("api.jamp.digital"), ConnectException(), SocketTimeoutException())
            .forEach { assertTrue(it.toString(), esTransitorio(it)) }
    }

    @Test fun servidorCaidoOSaturadoSeReintenta() {
        listOf(408, 429, 500, 502, 503, 504, 522, 530).forEach { assertTrue("$it", esTransitorio(HttpError(it, ""))) }
    }

    @Test fun errorDelClienteNoSeReintentaSolo() {
        listOf(400, 401, 403, 404, 411, 413).forEach { assertFalse("$it", esTransitorio(HttpError(it, ""))) }
        assertFalse(esTransitorio(IllegalStateException("bug")))
    }
}
