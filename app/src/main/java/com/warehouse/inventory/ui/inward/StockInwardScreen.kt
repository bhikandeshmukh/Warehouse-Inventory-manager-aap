package com.warehouse.inventory.ui.inward

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Inventory2
import androidx.compose.material.icons.filled.QrCodeScanner
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.warehouse.inventory.scanner.BarcodeScannerView

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StockInwardScreen(
    onBack: () -> Unit,
    viewModel: StockInwardViewModel = hiltViewModel()
) {
    val state by viewModel.uiState.collectAsState()
    val snackbarHost = remember { SnackbarHostState() }

    // Show confirmation snackbar
    LaunchedEffect(state.lastConfirmation) {
        state.lastConfirmation?.let {
            snackbarHost.showSnackbar(it)
            viewModel.clearConfirmation()
        }
    }

    // Show error snackbar
    LaunchedEffect(state.error) {
        state.error?.let {
            snackbarHost.showSnackbar("Error: $it")
            viewModel.clearError()
        }
    }

    // Scanner overlay
    if (state.scanTarget != null) {
        BarcodeScannerView(
            onResult = { viewModel.onBarcodeScanned(it) },
            onCancel = { viewModel.cancelScan() }
        )
        return
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Stock Inward") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primaryContainer,
                    titleContentColor = MaterialTheme.colorScheme.onPrimaryContainer
                )
            )
        },
        snackbarHost = { SnackbarHost(snackbarHost) }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 20.dp, vertical = 12.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // Header icon
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.3f)
                )
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    Icon(
                        Icons.Default.Inventory2,
                        contentDescription = null,
                        modifier = Modifier.size(32.dp),
                        tint = MaterialTheme.colorScheme.primary
                    )
                    Column {
                        Text("Add Stock", style = MaterialTheme.typography.titleMedium)
                        Text(
                            "Scan bin and SKU barcodes, then enter quantity",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f)
                        )
                    }
                }
            }

            // BIN Code
            OutlinedTextField(
                value = state.binCode,
                onValueChange = viewModel::onBinCodeChange,
                label = { Text("BIN Code") },
                placeholder = { Text("Scan or type bin location") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                trailingIcon = {
                    IconButton(onClick = { viewModel.startScan(ScanTarget.BIN) }) {
                        Icon(Icons.Default.QrCodeScanner, contentDescription = "Scan BIN")
                    }
                }
            )

            // SKU Code
            OutlinedTextField(
                value = state.skuCode,
                onValueChange = viewModel::onSkuCodeChange,
                label = { Text("SKU Code") },
                placeholder = { Text("Scan or type product code") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                trailingIcon = {
                    IconButton(onClick = { viewModel.startScan(ScanTarget.SKU) }) {
                        Icon(Icons.Default.QrCodeScanner, contentDescription = "Scan SKU")
                    }
                }
            )

            // Quantity
            OutlinedTextField(
                value = state.quantity,
                onValueChange = viewModel::onQuantityChange,
                label = { Text("Quantity") },
                placeholder = { Text("Enter quantity") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number)
            )

            // Note (optional)
            OutlinedTextField(
                value = state.note,
                onValueChange = viewModel::onNoteChange,
                label = { Text("Note (optional)") },
                placeholder = { Text("Add a note") },
                modifier = Modifier.fillMaxWidth(),
                minLines = 2,
                maxLines = 3
            )

            Spacer(Modifier.height(8.dp))

            // Submit button
            Button(
                onClick = viewModel::submit,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(56.dp),
                enabled = !state.isLoading
            ) {
                if (state.isLoading) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(24.dp),
                        color = MaterialTheme.colorScheme.onPrimary,
                        strokeWidth = 2.dp
                    )
                } else {
                    Icon(Icons.Default.Add, contentDescription = null)
                    Text("  Stock In", style = MaterialTheme.typography.titleMedium)
                }
            }

            // Reset button
            FilledTonalButton(
                onClick = viewModel::resetAll,
                modifier = Modifier.fillMaxWidth()
            ) {
                Text("Reset All Fields")
            }
        }
    }
}
