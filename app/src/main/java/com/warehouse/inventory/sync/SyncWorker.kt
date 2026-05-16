package com.warehouse.inventory.sync

import android.content.Context
import androidx.hilt.work.HiltWorker
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.warehouse.inventory.data.local.dao.BinDao
import com.warehouse.inventory.data.local.dao.SkuDao
import com.warehouse.inventory.data.local.dao.StockMovementDao
import com.warehouse.inventory.data.local.entities.SyncStatus
import com.warehouse.inventory.data.remote.api.SupabaseService
import com.warehouse.inventory.data.remote.dto.BinDto
import com.warehouse.inventory.data.remote.dto.SkuDto
import com.warehouse.inventory.data.remote.dto.StockMovementDto
import com.warehouse.inventory.data.repository.SessionManager
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import kotlinx.coroutines.flow.first
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

/**
 * Pushes locally-created data up to Supabase, batching by table.
 *
 * Order matters: bins and SKUs must exist before movements that reference them,
 * so we push masters first.
 *
 * On a successful push we mark each row as `synced`. Failures keep the row as
 * `pending` (with the error stored on stock_movements for debugging) so the
 * next run will retry.
 */
@HiltWorker
class SyncWorker @AssistedInject constructor(
    @Assisted ctx: Context,
    @Assisted params: WorkerParameters,
    private val binDao: BinDao,
    private val skuDao: SkuDao,
    private val movementDao: StockMovementDao,
    private val sessionManager: SessionManager,
    private val service: SupabaseService
) : CoroutineWorker(ctx, params) {

    override suspend fun doWork(): Result {
        val token = sessionManager.currentUser.first()?.token
            ?: return Result.retry() // not logged in yet
        return try {
            pushBins(token)
            pushSkus(token)
            pushMovements(token)
            Result.success()
        } catch (e: Exception) {
            // Transient failures (network) -> retry. WorkManager handles back-off.
            if (runAttemptCount < 5) Result.retry() else Result.failure()
        }
    }

    private suspend fun pushBins(token: String) {
        val pending = binDao.pendingSync()
        if (pending.isEmpty()) return
        val dtos = pending.map {
            BinDto(
                bin_code = it.binCode,
                description = it.description,
                zone = it.zone,
                is_active = it.isActive
            )
        }
        service.upsertBins(dtos, token).getOrThrow()
        pending.forEach { binDao.setSyncStatus(it.binCode, SyncStatus.SYNCED) }
    }

    private suspend fun pushSkus(token: String) {
        val pending = skuDao.pendingSync()
        if (pending.isEmpty()) return
        val dtos = pending.map {
            SkuDto(
                sku_code = it.skuCode,
                name = it.name,
                category = it.category,
                size = it.size,
                color = it.color,
                uom = it.uom,
                is_active = it.isActive
            )
        }
        service.upsertSkus(dtos, token).getOrThrow()
        pending.forEach { skuDao.setSyncStatus(it.skuCode, SyncStatus.SYNCED) }
    }

    private suspend fun pushMovements(token: String) {
        val pending = movementDao.pendingSync()
        if (pending.isEmpty()) return
        val dtos = pending.map {
            StockMovementDto(
                id = it.id,
                type = it.type,
                sku_code = it.skuCode,
                from_bin_code = it.fromBinCode,
                to_bin_code = it.toBinCode,
                quantity = it.quantity,
                performed_by = it.performedBy,
                note = it.note,
                created_at = formatTimestamp(it.createdAt)
            )
        }
        try {
            service.insertMovements(dtos, token).getOrThrow()
            pending.forEach { movementDao.setSyncStatus(it.id, SyncStatus.SYNCED) }
        } catch (e: Exception) {
            // Tag the rows so the UI can show the user what went wrong.
            pending.forEach {
                movementDao.setSyncStatus(it.id, SyncStatus.PENDING, e.message)
            }
            throw e
        }
    }

    private fun formatTimestamp(millis: Long): String {
        val fmt = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US)
        fmt.timeZone = TimeZone.getTimeZone("UTC")
        return fmt.format(Date(millis))
    }
}
