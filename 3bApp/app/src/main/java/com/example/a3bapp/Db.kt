package com.example.a3bapp

import android.content.Context
import androidx.room.Dao
import androidx.room.Database
import androidx.room.Delete
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.Update
import kotlinx.coroutines.flow.Flow

object Estado {
    const val PENDIENTE = "PENDIENTE" // guardada, aún sin respuesta del servidor (sin red, timeout o servidor caído)
    const val ENVIADA = "ENVIADA"     // el servidor ya respondió; resultadoJson tiene el JSON oficial
    const val ERROR = "ERROR"         // el servidor la rechazó (4xx) o se agotaron los intentos; solo se reintenta a mano
}

/** Una captura analizada, o guardada para analizar cuando haya red. Es la fila del historial. */
@Entity(tableName = "capturas")
data class Captura(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val creadaEn: Long,
    val estado: String,
    // JPEG ya reducidos, en filesDir/capturas: el envío pendiente no depende de la galería ni de la caché de la cámara
    val fachada: String,
    val producto: String,
    val etiqueta: String,
    // datos de la captura: lo que escribió el usuario al guardarla, y luego lo que detectó el servidor
    val tienda: String = "",
    val barcode: String = "",
    val precio: String = "",
    val marca: String = "",
    val nombre: String = "",
    val contenido: String = "",
    val unidad: String = "",
    val decision: String? = null,
    val motivo: String? = null,
    val resultadoJson: String? = null,
    val intentos: Int = 0,
    val error: String? = null,
)

@Dao
interface CapturaDao {
    @Insert suspend fun insertar(c: Captura): Long
    @Update suspend fun actualizar(c: Captura)
    @Delete suspend fun borrar(c: Captura)
    @Query("SELECT * FROM capturas WHERE id = :id") suspend fun get(id: Long): Captura?
    @Query("SELECT * FROM capturas WHERE id = :id") fun observar(id: Long): Flow<Captura?>
    @Query("SELECT * FROM capturas ORDER BY creadaEn DESC") fun observarTodas(): Flow<List<Captura>>
    @Query("SELECT id FROM capturas WHERE estado = 'PENDIENTE' ORDER BY creadaEn") suspend fun idsPendientes(): List<Long>
    @Query("SELECT COUNT(*) FROM capturas WHERE estado = 'PENDIENTE'") fun contarPendientes(): Flow<Int>
}

@Database(entities = [Captura::class], version = 1, exportSchema = false)
abstract class AppDb : RoomDatabase() {
    abstract fun dao(): CapturaDao

    companion object {
        @Volatile private var inst: AppDb? = null
        fun get(ctx: Context): AppDb = inst ?: synchronized(this) {
            inst ?: Room.databaseBuilder(ctx.applicationContext, AppDb::class.java, "3bapp.db").build().also { inst = it }
        }
    }
}
