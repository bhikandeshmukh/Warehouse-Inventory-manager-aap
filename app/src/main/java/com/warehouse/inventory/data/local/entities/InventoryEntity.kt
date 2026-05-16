package com.warehouse.inventory.data.local.entities

import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index

/**
 * Quantity of a given SKU in a given bin.
 * A single SKU can exist in multiple bins — that's what the composite PK enforces.
 */
@Entity(
    tableName = "inventory",
    primaryKeys = ["binCode", "skuCode"],
    foreignKeys = [
        ForeignKey(
            entity = BinEntity::class,
            parentColumns = ["binCode"],
            childColumns = ["binCode"],
            onDelete = ForeignKey.CASCADE
        ),
        ForeignKey(
            entity = SkuEntity::class,
            parentColumns = ["skuCode"],
            childColumns = ["skuCode"],
            onDelete = ForeignKey.CASCADE
        )
    ],
    indices = [Index("skuCode"), Index("binCode")]
)
data class InventoryEntity(
    val binCode: String,
    val skuCode: String,
    val quantity: Int,
    val updatedAt: Long = System.currentTimeMillis(),
    val syncStatus: String = SyncStatus.PENDING
)
