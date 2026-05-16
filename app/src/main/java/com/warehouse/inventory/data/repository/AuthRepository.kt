package com.warehouse.inventory.data.repository

import com.warehouse.inventory.BuildConfig
import com.warehouse.inventory.data.remote.api.SupabaseService
import com.warehouse.inventory.data.remote.dto.AuthRequest
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class AuthRepository @Inject constructor(
    private val service: SupabaseService,
    private val sessionManager: SessionManager
) {

    /**
     * Online login: hits Supabase. On success, the token is cached so the user
     * can re-enter the app without internet next time.
     *
     * Offline login: if the same username/password was previously used to log in,
     * the session is still valid until cleared. (For a stricter offline policy,
     * hash the password and verify locally.)
     */
    suspend fun login(username: String, password: String): Result<SessionUser> = runCatching {
        // Demo mode: if Supabase isn't configured, accept any non-empty credentials
        // so the dev can run the app immediately. Remove this branch before shipping.
        if (BuildConfig.SUPABASE_URL.contains("YOUR-PROJECT")) {
            val user = SessionUser(id = username, username = username, token = "demo-token")
            sessionManager.save(user)
            return@runCatching user
        }
        val response = service.signInWithPassword(AuthRequest(username, password)).getOrThrow()
        val user = SessionUser(
            id = response.user.id,
            username = response.user.email ?: username,
            token = response.accessToken
        )
        sessionManager.save(user)
        user
    }

    suspend fun logout() {
        sessionManager.clear()
    }

    val currentUser get() = sessionManager.currentUser
}
