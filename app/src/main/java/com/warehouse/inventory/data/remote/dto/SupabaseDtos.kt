package com.warehouse.inventory.data.remote.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class AuthRequest(
    val email: String,
    val password: String
)

@Serializable
data class AuthResponse(
    @SerialName("access_token") val accessToken: String,
    @SerialName("refresh_token") val refreshToken: String? = null,
    @SerialName("token_type") val tokenType: String = "bearer",
    @SerialName("expires_in") val expiresIn: Long = 0,
    val user: SupabaseUser
)

@Serializable
data class SupabaseUser(
    val id: String,
    val email: String? = null
)

@Serializable
data class BinDto(
    val bin_code: String,
    val description: String? = null,
    val zone: String? = null,
    val is_active: Boolean = true
)

@Serializable
data class SkuDto(
    val sku_code: String,
    val name: String,
    val category: String? = null,
    val size: String? = null,
    val color: String? = null,
    val uom: String = "PCS",
    val is_active: Boolean = true
)

@Serializable
data class StockMovementDto(
    val id: String,
    val type: String,
    val sku_code: String,
    val from_bin_code: String? = null,
    val to_bin_code: String? = null,
    val quantity: Int,
    val performed_by: String,
    val note: String? = null,
    val created_at: String
)
