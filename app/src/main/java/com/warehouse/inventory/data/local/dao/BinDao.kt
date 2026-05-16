package com.warehouse.inventory.data.local.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.warehouse.inventory.data.local.entities.BinEntity
import kotlinx.coroutines.flow.Flow

@Dao
interface BinDao {

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(bin: BinEntity)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertAll(bins: List<BinEntity>)

    @Query("SELECT * FROM bins WHERE binCode = :code LIMIT 1")
    suspend fun findByCode(code: String): BinEntity?

    @Query("SELECT * FROM bins WHERE isActive = 1 ORDER BY binCode")
    fun observeAllActive(): Flow<List<BinEntity>>

    @Query("SELECT COUNT(*) FROM bins")
    suspend fun count(): Int

    @Query("SELECT * FROM bins WHERE syncStatus = 'pending'")
    suspend fun pendingSync(): List<BinEntity>

    @Query("UPDATE bins SET syncStatus = :status WHERE binCode = :code")
    suspend fun setSyncStatus(code: String, status: String)
}
