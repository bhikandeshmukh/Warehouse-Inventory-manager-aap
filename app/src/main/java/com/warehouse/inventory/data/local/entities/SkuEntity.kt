package com.warehouse.inventory.data.local.entities

import androidx.room.Entity
import androidx.room.PrimaryKey

/**
 * A product SKU. The SKU code itself is the barcode (e.g. SKU-BLACK-KURTA-XL).
 */
@Entity(tableName = "skus")
data class SkuEntity(
    @PrimaryKey
    val skuCode: String,
    val name: String,
    val category: String? = null,
    val size: String? = null,
    val color: String? = null,
    val uom: String = "PCS",
    val isActive: Boolean = true,
    val createdAt: Long = System.currentTimeMillis(),
    val updatedAt: Long = System.currentTimeMillis(),
    val syncStatus: String = SyncStatus.PENDING
)
