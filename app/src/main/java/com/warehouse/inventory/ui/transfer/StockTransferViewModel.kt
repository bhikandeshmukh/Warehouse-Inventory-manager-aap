package com.warehouse.inventory.ui.transfer

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

data class TransferUiState(
    val fromBin: String = "",
    val toBin: String = "",
    val skuCode: String = "",
    val quantity: String = "",
    val note: String = "",
    val isLoading: Boolean = false,
    val error: String? = null,
    val lastConfirmation: String? = null,
    val scanTarget: TransferScanTarget? = null
)

enum class TransferScanTarget { FROM_BIN, TO_BIN, SKU }

@HiltViewModel
class StockTransferViewModel @Inject constructor(
    private val repository: InventoryRepository,
    private val sessionManager: SessionManager
) : ViewModel() {

    private val _uiState = MutableStateFlow(TransferUiState())
    val uiState: StateFlow<TransferUiState> = _uiState.asStateFlow()

    fun onFromBinChange(value: String) {
        _uiState.update { it.copy(fromBin = value, error = null) }
    }

    fun onToBinChange(value: String) {
        _uiState.update { it.copy(toBin = value, error = null) }
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
            TransferScanTarget.FROM_BIN -> _uiState.update { it.copy(fromBin = code, scanTarget = null) }
            TransferScanTarget.TO_BIN -> _uiState.update { it.copy(toBin = code, scanTarget = null) }
            TransferScanTarget.SKU -> _uiState.update { it.copy(skuCode = code, scanTarget = null) }
            null -> { /* ignored */ }
        }
    }

    fun startScan(target: TransferScanTarget) {
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
        if (state.fromBin.isBlank()) {
            _uiState.update { it.copy(error = "Scan or enter the source BIN") }
            return
        }
        if (state.toBin.isBlank()) {
            _uiState.update { it.copy(error = "Scan or enter the destination BIN") }
            return
        }
        if (state.fromBin.trim() == state.toBin.trim()) {
            _uiState.update { it.copy(error = "Source and destination must be different") }
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
            val result = repository.transfer(
                fromBin = state.fromBin.trim(),
                toBin = state.toBin.trim(),
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
                            lastConfirmation = "✓ ${mv.quantity} × ${mv.skuCode} moved ${state.fromBin} → ${state.toBin}"
                        )
                    }
                },
                onFailure = { e ->
                    _uiState.update {
                        it.copy(isLoading = false, error = e.message ?: "Transfer failed")
                    }
                }
            )
        }
    }

    fun resetAll() {
        _uiState.update { TransferUiState() }
    }
}
