package com.warehouse.inventory.ui.transfer

import androidx.compose.foundation.layout.Arrangement
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
import androidx.compose.material.icons.filled.MoveDown
import androidx.compose.material.icons.filled.QrCodeScanner
import androidx.compose.material.icons.filled.SwapHoriz
import androidx.compose.material3.Button
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
fun StockTransferScreen(
    onBack: () -> Unit,
    viewModel: StockTransferViewModel = hiltViewModel()
) {
    val state by viewModel.uiState.collectAsState()
    val snackbarHost = remember { SnackbarHostState() }

    LaunchedEffect(state.lastConfirmation) {
        state.lastConfirmation?.let {
            snackbarHost.showSnackbar(it)
            viewModel.clearConfirmation()
        }
    }

    LaunchedEffect(state.error) {
        state.error?.let {
            snackbarHost.showSnackbar("Error: $it")
            viewModel.clearError()
        }
    }

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
                title = { Text("Stock Transfer") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.tertiaryContainer,
                    titleContentColor = MaterialTheme.colorScheme.onTertiaryContainer
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
            // Header
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.tertiaryContainer.copy(alpha = 0.3f)
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
                        Icons.Default.MoveDown,
                        contentDescription = null,
                        modifier = Modifier.size(32.dp),
                        tint = MaterialTheme.colorScheme.tertiary
                    )
                    Column {
                        Text("Transfer Stock", style = MaterialTheme.typography.titleMedium)
                        Text(
                            "Move items between bin locations",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f)
                        )
                    }
                }
            }

            // From BIN
            OutlinedTextField(
                value = state.fromBin,
                onValueChange = viewModel::onFromBinChange,
                label = { Text("From BIN (Source)") },
                placeholder = { Text("Scan or type source bin") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                trailingIcon = {
                    IconButton(onClick = { viewModel.startScan(TransferScanTarget.FROM_BIN) }) {
                        Icon(Icons.Default.QrCodeScanner, contentDescription = "Scan source BIN")
                    }
                }
            )

            // To BIN
            OutlinedTextField(
                value = state.toBin,
                onValueChange = viewModel::onToBinChange,
                label = { Text("To BIN (Destination)") },
                placeholder = { Text("Scan or type destination bin") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                trailingIcon = {
                    IconButton(onClick = { viewModel.startScan(TransferScanTarget.TO_BIN) }) {
                        Icon(Icons.Default.QrCodeScanner, contentDescription = "Scan destination BIN")
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
                    IconButton(onClick = { viewModel.startScan(TransferScanTarget.SKU) }) {
                        Icon(Icons.Default.QrCodeScanner, contentDescription = "Scan SKU")
                    }
                }
            )

            // Quantity
            OutlinedTextField(
                value = state.quantity,
                onValueChange = viewModel::onQuantityChange,
                label = { Text("Quantity") },
                placeholder = { Text("Enter transfer quantity") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number)
            )

            // Note
            OutlinedTextField(
                value = state.note,
                onValueChange = viewModel::onNoteChange,
                label = { Text("Note (optional)") },
                placeholder = { Text("Reason for transfer") },
                modifier = Modifier.fillMaxWidth(),
                minLines = 2,
                maxLines = 3
            )

            Spacer(Modifier.height(8.dp))

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
                    Icon(Icons.Default.SwapHoriz, contentDescription = null)
                    Text("  Transfer Stock", style = MaterialTheme.typography.titleMedium)
                }
            }

            FilledTonalButton(
                onClick = viewModel::resetAll,
                modifier = Modifier.fillMaxWidth()
            ) {
                Text("Reset All Fields")
            }
        }
    }
}
