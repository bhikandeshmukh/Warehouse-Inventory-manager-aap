package com.warehouse.inventory.data.local.entities

import androidx.room.Entity
import androidx.room.PrimaryKey

/**
 * A warehouse bin / rack location, identified by its barcode (e.g. A-01-01).
 */
@Entity(tableName = "bins")
data class BinEntity(
    @PrimaryKey
    val binCode: String,
    val description: String? = null,
    val zone: String? = null,
    val isActive: Boolean = true,
    val createdAt: Long = System.currentTimeMillis(),
    val updatedAt: Long = System.currentTimeMillis(),
    val syncStatus: String = SyncStatus.PENDING
)

object SyncStatus {
    const val SYNCED = "synced"
    const val PENDING = "pending"
    const val FAILED = "failed"
}
