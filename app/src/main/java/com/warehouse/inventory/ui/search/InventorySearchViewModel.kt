package com.warehouse.inventory.ui.search

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.warehouse.inventory.data.local.dao.InventoryRow
import com.warehouse.inventory.data.repository.InventoryRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

data class SearchUiState(
    val query: String = "",
    val rows: List<InventoryRow> = emptyList(),
    val loading: Boolean = false,
    val error: String? = null
)

@HiltViewModel
class InventorySearchViewModel @Inject constructor(
    private val repo: InventoryRepository
) : ViewModel() {

    private val _state = MutableStateFlow(SearchUiState())
    val state: StateFlow<SearchUiState> = _state.asStateFlow()

    fun setQuery(value: String) {
        _state.update { it.copy(query = value) }
    }

    fun onScanned(code: String) {
        _state.update { it.copy(query = code) }
        runSearch()
    }

    fun runSearch() {
        val q = _state.value.query.trim()
        if (q.isEmpty()) return
        viewModelScope.launch {
            _state.update { it.copy(loading = true, error = null) }
            try {
                // Try SKU first, then BIN. The code is the same either way — we just
                // pick whichever lookup returns rows.
                val skuRows = repo.searchSku(q)
                val rows = if (skuRows.isNotEmpty()) skuRows else repo.searchBin(q)
                _state.update { it.copy(rows = rows, loading = false) }
            } catch (e: Exception) {
                _state.update { it.copy(loading = false, error = e.message) }
            }
        }
    }
}
