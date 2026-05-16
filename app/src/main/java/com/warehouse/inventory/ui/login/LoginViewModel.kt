package com.warehouse.inventory.ui.login

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.warehouse.inventory.data.repository.AuthRepository
import com.warehouse.inventory.sync.SyncManager
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

data class LoginUiState(
    val username: String = "",
    val password: String = "",
    val loading: Boolean = false,
    val error: String? = null,
    val loggedIn: Boolean = false
)

@HiltViewModel
class LoginViewModel @Inject constructor(
    private val auth: AuthRepository,
    private val syncManager: SyncManager
) : ViewModel() {

    private val _state = MutableStateFlow(LoginUiState())
    val state: StateFlow<LoginUiState> = _state.asStateFlow()

    val currentUser = auth.currentUser

    fun setUsername(value: String) = _state.update { it.copy(username = value, error = null) }
    fun setPassword(value: String) = _state.update { it.copy(password = value, error = null) }

    fun submit() {
        val s = _state.value
        if (s.username.isBlank() || s.password.isBlank()) {
            _state.update { it.copy(error = "Enter both username and password") }
            return
        }
        viewModelScope.launch {
            _state.update { it.copy(loading = true, error = null) }
            auth.login(s.username, s.password)
                .onSuccess {
                    syncManager.enqueuePeriodic()
                    _state.update { it.copy(loading = false, loggedIn = true) }
                }
                .onFailure { e ->
                    _state.update {
                        it.copy(
                            loading = false,
                            error = e.message ?: "Login failed"
                        )
                    }
                }
        }
    }
}
