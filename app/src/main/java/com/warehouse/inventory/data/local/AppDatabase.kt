package com.warehouse.inventory.data.local

import androidx.room.Database
import androidx.room.RoomDatabase
import com.warehouse.inventory.data.local.dao.BinDao
import com.warehouse.inventory.data.local.dao.InventoryDao
import com.warehouse.inventory.data.local.dao.SkuDao
import com.warehouse.inventory.data.local.dao.StockMovementDao
import com.warehouse.inventory.data.local.entities.BinEntity
import com.warehouse.inventory.data.local.entities.InventoryEntity
import com.warehouse.inventory.data.local.entities.SkuEntity
import com.warehouse.inventory.data.local.entities.StockMovementEntity

@Database(
    entities = [
        BinEntity::class,
        SkuEntity::class,
        InventoryEntity::class,
        StockMovementEntity::class
    ],
    version = 1,
    exportSchema = false
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun binDao(): BinDao
    abstract fun skuDao(): SkuDao
    abstract fun inventoryDao(): InventoryDao
    abstract fun stockMovementDao(): StockMovementDao

    companion object {
        const val DATABASE_NAME = "warehouse.db"
    }
}
