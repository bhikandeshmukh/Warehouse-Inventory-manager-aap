package com.warehouse.inventory.scanner

import android.annotation.SuppressLint
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import com.google.mlkit.vision.barcode.BarcodeScannerOptions
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.common.InputImage
import java.util.concurrent.atomic.AtomicBoolean

/**
 * CameraX [ImageAnalysis.Analyzer] that pipes frames into ML Kit's barcode scanner.
 *
 * Notes:
 *  - We only allow one in-flight ML Kit task at a time. Each frame that arrives
 *    while we're busy is closed immediately. This keeps memory bounded on
 *    cheaper devices that produce frames faster than they can be analysed.
 *  - We debounce duplicate reads of the same code within [debounceMillis] so a
 *    barcode held in view doesn't fire `onBarcode` 30 times per second.
 */
class BarcodeAnalyzer(
    private val debounceMillis: Long = 1500L,
    private val onBarcode: (String) -> Unit
) : ImageAnalysis.Analyzer {

    private val scanner = BarcodeScanning.getClient(
        BarcodeScannerOptions.Builder()
            .setBarcodeFormats(
                Barcode.FORMAT_CODE_128,
                Barcode.FORMAT_CODE_39,
                Barcode.FORMAT_CODE_93,
                Barcode.FORMAT_EAN_13,
                Barcode.FORMAT_EAN_8,
                Barcode.FORMAT_UPC_A,
                Barcode.FORMAT_UPC_E,
                Barcode.FORMAT_QR_CODE,
                Barcode.FORMAT_DATA_MATRIX,
                Barcode.FORMAT_ITF
            )
            .build()
    )

    private val busy = AtomicBoolean(false)
    @Volatile private var lastValue: String? = null
    @Volatile private var lastAt: Long = 0L

    @SuppressLint("UnsafeOptInUsageError")
    override fun analyze(image: ImageProxy) {
        if (!busy.compareAndSet(false, true)) {
            image.close()
            return
        }
        val media = image.image
        if (media == null) {
            busy.set(false)
            image.close()
            return
        }
        val input = InputImage.fromMediaImage(media, image.imageInfo.rotationDegrees)
        scanner.process(input)
            .addOnSuccessListener { codes ->
                val raw = codes.firstOrNull()?.rawValue
                if (!raw.isNullOrBlank()) emit(raw)
            }
            .addOnCompleteListener {
                busy.set(false)
                image.close()
            }
    }

    private fun emit(value: String) {
        val now = System.currentTimeMillis()
        if (value == lastValue && now - lastAt < debounceMillis) return
        lastValue = value
        lastAt = now
        onBarcode(value)
    }

    fun close() {
        scanner.close()
    }
}
