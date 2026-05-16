package com.warehouse.inventory.data.repository

import androidx.room.withTransaction
import com.warehouse.inventory.data.local.AppDatabase
import com.warehouse.inventory.data.local.dao.BinDao
import com.warehouse.inventory.data.local.dao.InventoryDao
import com.warehouse.inventory.data.local.dao.SkuDao
import com.warehouse.inventory.data.local.dao.StockMovementDao
import com.warehouse.inventory.data.local.entities.BinEntity
import com.warehouse.inventory.data.local.entities.InventoryEntity
import com.warehouse.inventory.data.local.entities.MovementType
import com.warehouse.inventory.data.local.entities.SkuEntity
import com.warehouse.inventory.data.local.entities.StockMovementEntity
import com.warehouse.inventory.data.local.entities.SyncStatus
import javax.inject.Inject
import javax.inject.Singleton

/**
 * All stock-changing operations route through here.
 *
 * Each operation does three things in a single Room transaction:
 *   1. Validate (bin exists, sku exists, enough stock to remove, etc.)
 *   2. Update the `inventory` row (insert/update/delete depending on quantity)
 *   3. Insert a `stock_movements` audit row marked `pending` for sync
 *
 * The audit row is the source of truth for the cloud — the sync layer pushes
 * `stock_movements`, and the server is responsible for re-applying them to its
 * inventory table. That way reconciliation is just "movements not yet acknowledged".
 */
@Singleton
class InventoryRepository @Inject constructor(
    private val db: AppDatabase,
    private val binDao: BinDao,
    private val skuDao: SkuDao,
    private val inventoryDao: InventoryDao,
    private val movementDao: StockMovementDao
) {

    // -------- Master data --------

    suspend fun ensureBin(code: String, description: String? = null): BinEntity {
        val existing = binDao.findByCode(code)
        if (existing != null) return existing
        val new = BinEntity(binCode = code, description = description)
        binDao.upsert(new)
        return new
    }

    suspend fun ensureSku(code: String, name: String? = null): SkuEntity {
        val existing = skuDao.findByCode(code)
        if (existing != null) return existing
        val new = SkuEntity(skuCode = code, name = name ?: code)
        skuDao.upsert(new)
        return new
    }

    suspend fun getBin(code: String) = binDao.findByCode(code)
    suspend fun getSku(code: String) = skuDao.findByCode(code)

    fun observeAllBins() = binDao.observeAllActive()
    fun observeAllSkus() = skuDao.observeAllActive()
    fun observeAllInventory() = inventoryDao.observeAll()
    fun observeSkuSummary() = inventoryDao.observeSkuSummary()
    fun observeRecentMovements(limit: Int = 100) = movementDao.observeRecent(limit)
    fun observePendingSyncCount() = movementDao.observePendingCount()

    suspend fun searchSku(code: String) = inventoryDao.rowsForSku(code)
    suspend fun searchBin(code: String) = inventoryDao.rowsForBin(code)

    // -------- Stock movements --------

    /**
     * Stock IN: add `quantity` of `sku` into `bin`. Auto-creates master rows if missing
     * (useful when scanning a brand-new bin label or product barcode for the first time).
     */
    suspend fun stockIn(
        binCode: String,
        skuCode: String,
        quantity: Int,
        performedBy: String,
        note: String? = null
    ): Result<StockMovementEntity> = runCatching {
        require(quantity > 0) { "Quantity must be positive" }
        db.withTransaction {
            ensureBin(binCode)
            ensureSku(skuCode)
            val existing = inventoryDao.find(binCode, skuCode)
            val newQty = (existing?.quantity ?: 0) + quantity
            inventoryDao.upsert(
                InventoryEntity(
                    binCode = binCode,
                    skuCode = skuCode,
                    quantity = newQty,
                    syncStatus = SyncStatus.PENDING
                )
            )
            val mv = StockMovementEntity(
                type = MovementType.INWARD,
                skuCode = skuCode,
                toBinCode = binCode,
                quantity = quantity,
                performedBy = performedBy,
                note = note
            )
            movementDao.insert(mv)
            mv
        }
    }

    /**
     * Stock OUT: remove `quantity` of `sku` from `bin`. Errors out if not enough stock.
     */
    suspend fun stockOut(
        binCode: String,
        skuCode: String,
        quantity: Int,
        performedBy: String,
        note: String? = null
    ): Result<StockMovementEntity> = runCatching {
        require(quantity > 0) { "Quantity must be positive" }
        db.withTransaction {
            val existing = inventoryDao.find(binCode, skuCode)
                ?: throw IllegalStateException("No stock of $skuCode in bin $binCode")
            if (existing.quantity < quantity) {
                throw IllegalStateException(
                    "Insufficient stock: have ${existing.quantity}, need $quantity"
                )
            }
            val newQty = existing.quantity - quantity
            if (newQty == 0) {
                inventoryDao.delete(binCode, skuCode)
            } else {
                inventoryDao.upsert(
                    existing.copy(
                        quantity = newQty,
                        updatedAt = System.currentTimeMillis(),
                        syncStatus = SyncStatus.PENDING
                    )
                )
            }
            val mv = StockMovementEntity(
                type = MovementType.OUTWARD,
                skuCode = skuCode,
                fromBinCode = binCode,
                quantity = quantity,
                performedBy = performedBy,
                note = note
            )
            movementDao.insert(mv)
            mv
        }
    }

    /**
     * Stock TRANSFER: move `quantity` of `sku` from one bin to another atomically.
     */
    suspend fun transfer(
        fromBin: String,
        toBin: String,
        skuCode: String,
        quantity: Int,
        performedBy: String,
        note: String? = null
    ): Result<StockMovementEntity> = runCatching {
        require(quantity > 0) { "Quantity must be positive" }
        require(fromBin != toBin) { "Source and destination bin must differ" }
        db.withTransaction {
            ensureBin(toBin)
            val source = inventoryDao.find(fromBin, skuCode)
                ?: throw IllegalStateException("No stock of $skuCode in bin $fromBin")
            if (source.quantity < quantity) {
                throw IllegalStateException(
                    "Insufficient stock: have ${source.quantity}, need $quantity"
                )
            }
            // decrement source
            val newSource = source.quantity - quantity
            if (newSource == 0) {
                inventoryDao.delete(fromBin, skuCode)
            } else {
                inventoryDao.upsert(
                    source.copy(
                        quantity = newSource,
                        updatedAt = System.currentTimeMillis(),
                        syncStatus = SyncStatus.PENDING
                    )
                )
            }
            // increment destination
            val dest = inventoryDao.find(toBin, skuCode)
            inventoryDao.upsert(
                InventoryEntity(
                    binCode = toBin,
                    skuCode = skuCode,
                    quantity = (dest?.quantity ?: 0) + quantity,
                    syncStatus = SyncStatus.PENDING
                )
            )
            val mv = StockMovementEntity(
                type = MovementType.TRANSFER,
                skuCode = skuCode,
                fromBinCode = fromBin,
                toBinCode = toBin,
                quantity = quantity,
                performedBy = performedBy,
                note = note
            )
            movementDao.insert(mv)
            mv
        }
    }
}
