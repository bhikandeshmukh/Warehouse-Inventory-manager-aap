package com.warehouse.inventory.data.local.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.warehouse.inventory.data.local.entities.InventoryEntity
import kotlinx.coroutines.flow.Flow

/**
 * Result row used by inventory search.
 * Joined with sku name so we can show a human-readable name with each row.
 */
data class InventoryRow(
    val binCode: String,
    val skuCode: String,
    val name: String?,
    val quantity: Int,
    val updatedAt: Long
)

data class SkuBinSummary(
    val skuCode: String,
    val name: String?,
    val totalQuantity: Int,
    val binCount: Int
)

@Dao
interface InventoryDao {

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(row: InventoryEntity)

    @Query("SELECT * FROM inventory WHERE binCode = :bin AND skuCode = :sku LIMIT 1")
    suspend fun find(bin: String, sku: String): InventoryEntity?

    @Query("DELETE FROM inventory WHERE binCode = :bin AND skuCode = :sku")
    suspend fun delete(bin: String, sku: String)

    @Query("""
        SELECT i.binCode AS binCode,
               i.skuCode AS skuCode,
               s.name    AS name,
               i.quantity AS quantity,
               i.updatedAt AS updatedAt
        FROM inventory i
        LEFT JOIN skus s ON s.skuCode = i.skuCode
        WHERE i.skuCode = :sku AND i.quantity > 0
        ORDER BY i.binCode
    """)
    suspend fun rowsForSku(sku: String): List<InventoryRow>

    @Query("""
        SELECT i.binCode AS binCode,
               i.skuCode AS skuCode,
               s.name    AS name,
               i.quantity AS quantity,
               i.updatedAt AS updatedAt
        FROM inventory i
        LEFT JOIN skus s ON s.skuCode = i.skuCode
        WHERE i.binCode = :bin AND i.quantity > 0
        ORDER BY i.skuCode
    """)
    suspend fun rowsForBin(bin: String): List<InventoryRow>

    @Query("""
        SELECT i.binCode AS binCode,
               i.skuCode AS skuCode,
               s.name    AS name,
               i.quantity AS quantity,
               i.updatedAt AS updatedAt
        FROM inventory i
        LEFT JOIN skus s ON s.skuCode = i.skuCode
        WHERE i.quantity > 0
        ORDER BY i.skuCode, i.binCode
    """)
    fun observeAll(): Flow<List<InventoryRow>>

    @Query("""
        SELECT i.skuCode AS skuCode,
               s.name AS name,
               SUM(i.quantity) AS totalQuantity,
               COUNT(DISTINCT i.binCode) AS binCount
        FROM inventory i
        LEFT JOIN skus s ON s.skuCode = i.skuCode
        WHERE i.quantity > 0
        GROUP BY i.skuCode
        ORDER BY s.name
    """)
    fun observeSkuSummary(): Flow<List<SkuBinSummary>>

    @Query("SELECT COALESCE(SUM(quantity), 0) FROM inventory WHERE skuCode = :sku")
    suspend fun totalForSku(sku: String): Int

    @Query("SELECT COALESCE(SUM(quantity), 0) FROM inventory WHERE binCode = :bin")
    suspend fun totalForBin(bin: String): Int

    @Query("SELECT * FROM inventory")
    suspend fun all(): List<InventoryEntity>
}
