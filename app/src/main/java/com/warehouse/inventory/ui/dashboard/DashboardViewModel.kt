package com.warehouse.inventory.ui.dashboard

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.warehouse.inventory.data.repository.AuthRepository
import com.warehouse.inventory.data.repository.InventoryRepository
import com.warehouse.inventory.sync.SyncManager
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class DashboardViewModel @Inject constructor(
    private val auth: AuthRepository,
    inventory: InventoryRepository,
    private val syncManager: SyncManager
) : ViewModel() {

    val currentUser = auth.currentUser
    val pendingSyncCount = inventory.observePendingSyncCount()

    fun triggerSync() = syncManager.enqueueOneShot()

    fun logout(onDone: () -> Unit) {
        viewModelScope.launch {
            auth.logout()
            onDone()
        }
    }
}
