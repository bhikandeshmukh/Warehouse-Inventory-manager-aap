package com.warehouse.inventory.data.local.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.warehouse.inventory.data.local.entities.SkuEntity
import kotlinx.coroutines.flow.Flow

@Dao
interface SkuDao {

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(sku: SkuEntity)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertAll(skus: List<SkuEntity>)

    @Query("SELECT * FROM skus WHERE skuCode = :code LIMIT 1")
    suspend fun findByCode(code: String): SkuEntity?

    @Query("SELECT * FROM skus WHERE isActive = 1 ORDER BY skuCode")
    fun observeAllActive(): Flow<List<SkuEntity>>

    @Query("SELECT COUNT(*) FROM skus")
    suspend fun count(): Int

    @Query("SELECT * FROM skus WHERE syncStatus = 'pending'")
    suspend fun pendingSync(): List<SkuEntity>

    @Query("UPDATE skus SET syncStatus = :status WHERE skuCode = :code")
    suspend fun setSyncStatus(code: String, status: String)
}
