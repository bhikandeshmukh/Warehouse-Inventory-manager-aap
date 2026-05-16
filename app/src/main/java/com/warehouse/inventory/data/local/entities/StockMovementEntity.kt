package com.warehouse.inventory.data.local.entities

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey
import java.util.UUID

/**
 * Every inventory change (inward, outward, transfer) is recorded here.
 * `id` is generated client-side as a UUID so movements created offline
 * have a stable identity when synced.
 */
@Entity(
    tableName = "stock_movements",
    indices = [Index("syncStatus"), Index("skuCode"), Index("createdAt")]
)
data class StockMovementEntity(
    @PrimaryKey
    val id: String = UUID.randomUUID().toString(),
    val type: String,                  // see MovementType
    val skuCode: String,
    val fromBinCode: String? = null,   // null for INWARD
    val toBinCode: String? = null,     // null for OUTWARD
    val quantity: Int,
    val performedBy: String,           // user id / username
    val note: String? = null,
    val createdAt: Long = System.currentTimeMillis(),
    val syncStatus: String = SyncStatus.PENDING,
    val lastSyncError: String? = null
)

object MovementType {
    const val INWARD = "INWARD"
    const val OUTWARD = "OUTWARD"
    const val TRANSFER = "TRANSFER"
    const val ADJUSTMENT = "ADJUSTMENT"
}
