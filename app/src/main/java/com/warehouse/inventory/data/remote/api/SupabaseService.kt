package com.warehouse.inventory.data.remote.api

import com.warehouse.inventory.BuildConfig
import com.warehouse.inventory.data.remote.dto.AuthRequest
import com.warehouse.inventory.data.remote.dto.AuthResponse
import com.warehouse.inventory.data.remote.dto.BinDto
import com.warehouse.inventory.data.remote.dto.SkuDto
import com.warehouse.inventory.data.remote.dto.StockMovementDto
import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.request.headers
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.HttpResponse
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.contentType
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Thin wrapper around the Supabase REST and Auth endpoints we use.
 *
 * Why hand-rolled instead of the official supabase-kt SDK? The SDK is great,
 * but pulls in a lot of transitive deps and ships its own coroutine scope.
 * This module only needs auth + a couple of `POST /rest/v1/<table>` calls,
 * so a small Ktor wrapper is lighter and easier to mock in tests.
 *
 * Replace with supabase-kt later if you want realtime subscriptions, storage, etc.
 */
@Singleton
class SupabaseService @Inject constructor(
    private val client: HttpClient
) {
    private val baseUrl = BuildConfig.SUPABASE_URL.trimEnd('/')
    private val anonKey = BuildConfig.SUPABASE_ANON_KEY

    suspend fun signInWithPassword(req: AuthRequest): Result<AuthResponse> = runCatching {
        val resp = client.post("$baseUrl/auth/v1/token?grant_type=password") {
            commonHeaders(useAnon = true)
            contentType(ContentType.Application.Json)
            setBody(req)
        }
        resp.requireSuccess()
        resp.body<AuthResponse>()
    }

    suspend fun upsertBins(rows: List<BinDto>, accessToken: String): Result<Unit> =
        upsertRows("bins", rows, accessToken)

    suspend fun upsertSkus(rows: List<SkuDto>, accessToken: String): Result<Unit> =
        upsertRows("skus", rows, accessToken)

    suspend fun insertMovements(rows: List<StockMovementDto>, accessToken: String): Result<Unit> =
        upsertRows("stock_movements", rows, accessToken)

    private suspend inline fun <reified T> upsertRows(
        table: String,
        rows: List<T>,
        accessToken: String
    ): Result<Unit> = runCatching {
        if (rows.isEmpty()) return@runCatching Unit
        val resp = client.post("$baseUrl/rest/v1/$table") {
            commonHeaders(useAnon = false)
            headers {
                append(HttpHeaders.Authorization, "Bearer $accessToken")
                // Upsert + ignore returning to keep payload small
                append("Prefer", "resolution=merge-duplicates,return=minimal")
            }
            contentType(ContentType.Application.Json)
            setBody(rows)
        }
        resp.requireSuccess()
        Unit
    }

    private fun io.ktor.client.request.HttpRequestBuilder.commonHeaders(useAnon: Boolean) {
        headers {
            append("apikey", anonKey)
            if (useAnon) append(HttpHeaders.Authorization, "Bearer $anonKey")
            append(HttpHeaders.Accept, ContentType.Application.Json.toString())
        }
    }

    private fun HttpResponse.requireSuccess() {
        val s = status
        if (s != HttpStatusCode.OK &&
            s != HttpStatusCode.Created &&
            s != HttpStatusCode.NoContent &&
            s != HttpStatusCode.Accepted) {
            error("Supabase request failed: ${s.value} ${s.description}")
        }
    }
}
