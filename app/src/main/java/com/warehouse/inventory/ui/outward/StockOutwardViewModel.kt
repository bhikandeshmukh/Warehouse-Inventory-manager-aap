package com.warehouse.inventory.ui.outward

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.warehouse.inventory.data.repository.InventoryRepository
import com.warehouse.inventory.data.repository.SessionManager
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

data class OutwardUiState(
    val binCode: String = "",
    val skuCode: String = "",
    val quantity: String = "",
    val note: String = "",
    val isLoading: Boolean = false,
    val error: String? = null,
    val lastConfirmation: String? = null,
    val scanTarget: OutwardScanTarget? = null
)

enum class OutwardScanTarget { BIN, SKU }

@HiltViewModel
class StockOutwardViewModel @Inject constructor(
    private val repository: InventoryRepository,
    private val sessionManager: SessionManager
) : ViewModel() {

    private val _uiState = MutableStateFlow(OutwardUiState())
    val uiState: StateFlow<OutwardUiState> = _uiState.asStateFlow()

    fun onBinCodeChange(value: String) {
        _uiState.update { it.copy(binCode = value, error = null) }
    }

    fun onSkuCodeChange(value: String) {
        _uiState.update { it.copy(skuCode = value, error = null) }
    }

    fun onQuantityChange(value: String) {
        _uiState.update { it.copy(quantity = value, error = null) }
    }

    fun onNoteChange(value: String) {
        _uiState.update { it.copy(note = value) }
    }

    fun onBarcodeScanned(code: String) {
        when (_uiState.value.scanTarget) {
            OutwardScanTarget.BIN -> _uiState.update { it.copy(binCode = code, scanTarget = null) }
            OutwardScanTarget.SKU -> _uiState.update { it.copy(skuCode = code, scanTarget = null) }
            null -> { /* ignored */ }
        }
    }

    fun startScan(target: OutwardScanTarget) {
        _uiState.update { it.copy(scanTarget = target) }
    }

    fun cancelScan() {
        _uiState.update { it.copy(scanTarget = null) }
    }

    fun clearError() {
        _uiState.update { it.copy(error = null) }
    }

    fun clearConfirmation() {
        _uiState.update { it.copy(lastConfirmation = null) }
    }

    fun submit() {
        val state = _uiState.value
        val qty = state.quantity.toIntOrNull()
        if (state.binCode.isBlank()) {
            _uiState.update { it.copy(error = "Scan or enter a BIN code") }
            return
        }
        if (state.skuCode.isBlank()) {
            _uiState.update { it.copy(error = "Scan or enter a SKU code") }
            return
        }
        if (qty == null || qty <= 0) {
            _uiState.update { it.copy(error = "Enter a valid quantity") }
            return
        }

        viewModelScope.launch {
            _uiState.update { it.copy(isLoading = true, error = null) }
            val user = sessionManager.currentUser.first()?.username ?: "unknown"
            val result = repository.stockOut(
                binCode = state.binCode.trim(),
                skuCode = state.skuCode.trim(),
                quantity = qty,
                performedBy = user,
                note = state.note.takeIf { it.isNotBlank() }
            )
            result.fold(
                onSuccess = { mv ->
                    _uiState.update {
                        it.copy(
                            skuCode = "",
                            quantity = "",
                            note = "",
                            isLoading = false,
                            lastConfirmation = "✓ ${mv.quantity} × ${mv.skuCode} dispatched from ${state.binCode}"
                        )
                    }
                },
                onFailure = { e ->
                    _uiState.update {
                        it.copy(isLoading = false, error = e.message ?: "Stock-out failed")
                    }
                }
            )
        }
    }

    fun resetAll() {
        _uiState.update { OutwardUiState() }
    }
}
