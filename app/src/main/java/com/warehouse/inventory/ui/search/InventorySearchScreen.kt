package com.warehouse.inventory.ui.search

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.QrCodeScanner
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.warehouse.inventory.scanner.BarcodeScannerView

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun InventorySearchScreen(
    viewModel: InventorySearchViewModel = hiltViewModel(),
    onBack: () -> Unit
) {
    val state by viewModel.state.collectAsState()
    var scannerOpen by remember { mutableStateOf(false) }

    if (scannerOpen) {
        BarcodeScannerView(
            hint = "Scan a SKU or BIN barcode",
            onResult = {
                viewModel.onScanned(it)
                scannerOpen = false
            },
            onCancel = { scannerOpen = false }
        )
        return
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Inventory Search") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                }
            )
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp)
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                OutlinedTextField(
                    value = state.query,
                    onValueChange = viewModel::setQuery,
                    label = { Text("SKU or BIN code") },
                    modifier = Modifier.weight(1f),
                    singleLine = true,
                    trailingIcon = {
                        IconButton(onClick = viewModel::runSearch) {
                            Icon(Icons.Default.Search, contentDescription = "Search")
                        }
                    }
                )
                Spacer(Modifier.width(8.dp))
                IconButton(onClick = { scannerOpen = true }) {
                    Icon(Icons.Default.QrCodeScanner, contentDescription = "Scan")
                }
            }
            Spacer(Modifier.height(8.dp))

            state.error?.let {
                Text(it, color = MaterialTheme.colorScheme.error)
                Spacer(Modifier.height(8.dp))
            }

            if (state.rows.isNotEmpty()) {
                Text(
                    "TOTAL = ${state.rows.sumOf { it.quantity }}",
                    style = MaterialTheme.typography.titleLarge
                )
                Spacer(Modifier.height(8.dp))
                LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    items(state.rows) { row ->
                        Card {
                            Column(Modifier.padding(12.dp)) {
                                Text(
                                    "${row.binCode}  =  ${row.quantity}",
                                    style = MaterialTheme.typography.titleLarge
                                )
                                Text(
                                    "${row.skuCode} — ${row.name ?: ""}",
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f)
                                )
                            }
                        }
                    }
                }
            } else if (state.query.isNotBlank() && !state.loading) {
                Text("No stock found for '${state.query}'.")
            }
        }
    }
}
