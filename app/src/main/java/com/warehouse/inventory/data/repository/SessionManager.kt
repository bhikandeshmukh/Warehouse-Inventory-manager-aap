package com.warehouse.inventory.data.repository

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import javax.inject.Inject
import javax.inject.Singleton

private val Context.sessionDataStore by preferencesDataStore(name = "session")

@Singleton
class SessionManager @Inject constructor(
    @ApplicationContext private val context: Context
) {
    private val userIdKey = stringPreferencesKey("user_id")
    private val usernameKey = stringPreferencesKey("username")
    private val tokenKey = stringPreferencesKey("token")

    val currentUser: Flow<SessionUser?> =
        context.sessionDataStore.data.map { prefs ->
            val id = prefs[userIdKey] ?: return@map null
            val name = prefs[usernameKey] ?: id
            val tok = prefs[tokenKey]
            SessionUser(id = id, username = name, token = tok)
        }

    suspend fun save(user: SessionUser) {
        context.sessionDataStore.edit { prefs ->
            prefs[userIdKey] = user.id
            prefs[usernameKey] = user.username
            user.token?.let { prefs[tokenKey] = it }
        }
    }

    suspend fun clear() {
        context.sessionDataStore.edit { it.clear() }
    }
}

data class SessionUser(
    val id: String,
    val username: String,
    val token: String? = null
)
