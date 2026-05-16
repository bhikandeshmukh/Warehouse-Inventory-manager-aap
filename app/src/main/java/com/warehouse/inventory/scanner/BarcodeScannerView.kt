package com.warehouse.inventory.scanner

import android.Manifest
import android.content.Context
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import com.google.accompanist.permissions.ExperimentalPermissionsApi
import com.google.accompanist.permissions.isGranted
import com.google.accompanist.permissions.rememberPermissionState
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

/**
 * Drop-in barcode scanner view.
 *
 * Caller passes [onResult]; it'll fire once per debounced scan. The hosting
 * screen is responsible for closing/popping its scanner state after a hit.
 */
@OptIn(ExperimentalPermissionsApi::class)
@Composable
fun BarcodeScannerView(
    modifier: Modifier = Modifier,
    hint: String = "Point the camera at a barcode",
    onResult: (String) -> Unit,
    onCancel: () -> Unit
) {
    val cameraPermission = rememberPermissionState(Manifest.permission.CAMERA)
    if (!cameraPermission.status.isGranted) {
        Column(
            modifier = modifier
                .fillMaxSize()
                .background(MaterialTheme.colorScheme.background)
                .padding(24.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text(
                text = "Camera permission is required to scan barcodes.",
                style = MaterialTheme.typography.bodyLarge
            )
            Spacer(Modifier.height(16.dp))
            Button(onClick = { cameraPermission.launchPermissionRequest() }) {
                Text("Grant permission")
            }
            Spacer(Modifier.height(8.dp))
            Button(onClick = onCancel) { Text("Cancel") }
        }
        return
    }

    Box(modifier = modifier.fillMaxSize().background(Color.Black)) {
        CameraPreview(onBarcode = onResult)

        // Translucent overlay with a viewfinder
        Box(
            modifier = Modifier
                .align(Alignment.Center)
                .fillMaxWidth(0.8f)
                .height(220.dp)
                .border(2.dp, Color.White, RoundedCornerShape(12.dp))
        )

        Column(
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .fillMaxWidth()
                .padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text(
                text = hint,
                color = Color.White,
                style = MaterialTheme.typography.bodyLarge
            )
            Spacer(Modifier.height(12.dp))
            Button(onClick = onCancel) { Text("Cancel") }
        }
    }
}

@Composable
private fun CameraPreview(onBarcode: (String) -> Unit) {
    val ctx = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val onBarcodeState by rememberUpdatedState(onBarcode)

    // Single-thread analysis executor — frames are dropped, not queued.
    val analysisExecutor = remember<ExecutorService> { Executors.newSingleThreadExecutor() }
    var analyzer by remember { mutableStateOf<BarcodeAnalyzer?>(null) }

    DisposableEffect(Unit) {
        onDispose {
            analyzer?.close()
            analysisExecutor.shutdown()
        }
    }

    AndroidView(
        modifier = Modifier.fillMaxSize(),
        factory = { context ->
            val previewView = PreviewView(context).apply {
                scaleType = PreviewView.ScaleType.FILL_CENTER
            }
            bindCamera(
                context = context,
                lifecycleOwner = lifecycleOwner,
                previewView = previewView,
                analysisExecutor = analysisExecutor,
                onAnalyzerCreated = { analyzer = it },
                onBarcode = { onBarcodeState(it) }
            )
            previewView
        }
    )
}

private fun bindCamera(
    context: Context,
    lifecycleOwner: androidx.lifecycle.LifecycleOwner,
    previewView: PreviewView,
    analysisExecutor: ExecutorService,
    onAnalyzerCreated: (BarcodeAnalyzer) -> Unit,
    onBarcode: (String) -> Unit
) {
    val providerFuture = ProcessCameraProvider.getInstance(context)
    providerFuture.addListener({
        val provider = providerFuture.get()
        val preview = Preview.Builder().build().apply {
            setSurfaceProvider(previewView.surfaceProvider)
        }
        val analyzer = BarcodeAnalyzer(onBarcode = onBarcode)
        onAnalyzerCreated(analyzer)
        val analysis = ImageAnalysis.Builder()
            .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
            .build()
            .also { it.setAnalyzer(analysisExecutor, analyzer) }

        provider.unbindAll()
        provider.bindToLifecycle(
            lifecycleOwner,
            CameraSelector.DEFAULT_BACK_CAMERA,
            preview,
            analysis
        )
    }, ContextCompat.getMainExecutor(context))
}
