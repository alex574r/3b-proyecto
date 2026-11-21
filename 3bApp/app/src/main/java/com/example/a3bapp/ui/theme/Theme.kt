package com.example.a3bapp.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.lightColorScheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

val Brand = Color(0xFFE81C24)
val Paper = Color(0xFFFEFDFD)
val Ink = Color(0xFF25181D)
val Muted = Color(0xFF67575D)
val Line = Color(0xFFE4D6D9)
val Wash = Color(0xFFF7EBED)
val Canvas = Color(0xFFFBF6F6)
val Success = Color(0xFF176749)
val SuccessBg = Color(0xFFE0F4E9)
val Pending = Color(0xFF855212)
val PendingBg = Color(0xFFFFF0D6)
val Danger = Color(0xFFAA2331)

private val Colors = lightColorScheme(
    primary = Brand, onPrimary = Paper, primaryContainer = Wash, onPrimaryContainer = Ink,
    secondary = Success, onSecondary = Paper, secondaryContainer = SuccessBg, onSecondaryContainer = Success,
    tertiary = Pending, onTertiary = Paper, tertiaryContainer = PendingBg, onTertiaryContainer = Pending,
    error = Danger, errorContainer = Wash, onError = Paper, onErrorContainer = Danger,
    surface = Paper, onSurface = Ink, surfaceVariant = Wash, onSurfaceVariant = Muted,
    background = Canvas, onBackground = Ink, outline = Line, outlineVariant = Line,
)

@Composable
fun _3bAppTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = Colors,
        typography = Typography,
        shapes = Shapes(
            small = RoundedCornerShape(11.dp),
            medium = RoundedCornerShape(16.dp),
            large = RoundedCornerShape(20.dp),
        ),
        content = content,
    )
}
