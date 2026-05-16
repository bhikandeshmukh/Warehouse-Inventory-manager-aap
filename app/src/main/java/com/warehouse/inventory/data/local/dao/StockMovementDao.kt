package com.warehouse.inventory.data.local.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.warehouse.inventory.data.local.entities.StockMovementEntity
import kotlinx.coroutines.flow.Flow

@Dao
interface StockMovementDao {

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(movement: StockMovementEntity)

    @Query("SELECT * FROM stock_movements ORDER BY createdAt DESC LIMIT :limit")
    fun observeRecent(limit: Int = 100): Flow<List<StockMovementEntity>>

    @Query("SELECT * FROM stock_movements WHERE syncStatus = 'pending' ORDER BY createdAt ASC")
    suspend fun pendingSync(): List<StockMovementEntity>

    @Query("SELECT COUNT(*) FROM stock_movements WHERE syncStatus = 'pending'")
    fun observePendingCount(): Flow<Int>

    @Query("UPDATE stock_movements SET syncStatus = :status, lastSyncError = :error WHERE id = :id")
    suspend fun setSyncStatus(id: String, status: String, error: String? = null)

    @Query("SELECT * FROM stock_movements WHERE skuCode = :sku ORDER BY createdAt DESC LIMIT :limit")
    suspend fun forSku(sku: String, limit: Int = 100): List<StockMovementEntity>
}
