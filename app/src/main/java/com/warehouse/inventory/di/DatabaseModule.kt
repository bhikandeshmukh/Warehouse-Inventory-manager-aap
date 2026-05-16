package com.warehouse.inventory.di

import android.content.Context
import androidx.room.Room
import com.warehouse.inventory.data.local.AppDatabase
import com.warehouse.inventory.data.local.dao.BinDao
import com.warehouse.inventory.data.local.dao.InventoryDao
import com.warehouse.inventory.data.local.dao.SkuDao
import com.warehouse.inventory.data.local.dao.StockMovementDao
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object DatabaseModule {

    @Provides
    @Singleton
    fun provideDatabase(@ApplicationContext ctx: Context): AppDatabase =
        Room.databaseBuilder(ctx, AppDatabase::class.java, AppDatabase.DATABASE_NAME)
            // For early dev, drop on schema change. Replace with proper Migrations before release.
            .fallbackToDestructiveMigration()
            .build()

    @Provides fun provideBinDao(db: AppDatabase): BinDao = db.binDao()
    @Provides fun provideSkuDao(db: AppDatabase): SkuDao = db.skuDao()
    @Provides fun provideInventoryDao(db: AppDatabase): InventoryDao = db.inventoryDao()
    @Provides fun provideMovementDao(db: AppDatabase): StockMovementDao = db.stockMovementDao()
}
