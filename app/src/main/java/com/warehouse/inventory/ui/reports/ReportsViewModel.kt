package com.warehouse.inventory.ui.reports

import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.core.content.FileProvider
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.warehouse.inventory.data.local.dao.BinDao
import com.warehouse.inventory.data.local.dao.InventoryDao
import com.warehouse.inventory.data.local.dao.SkuDao
import com.warehouse.inventory.data.local.dao.StockMovementDao
import com.warehouse.inventory.data.local.entities.BinEntity
import com.warehouse.inventory.data.local.entities.InventoryEntity
import com.warehouse.inventory.data.local.entities.SkuEntity
import com.warehouse.inventory.data.repository.InventoryRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.apache.poi.ss.usermodel.FillPatternType
import org.apache.poi.ss.usermodel.HorizontalAlignment
import org.apache.poi.ss.usermodel.IndexedColors
import org.apache.poi.xssf.usermodel.XSSFWorkbook
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import javax.inject.Inject

data class ReportsUiState(
    val isExporting: Boolean = false,
    val isImporting: Boolean = false,
    val message: String? = null,
    val error: String? = null
)

@HiltViewModel
class ReportsViewModel @Inject constructor(
    @ApplicationContext private val context: Context,
    private val inventoryDao: InventoryDao,
    private val binDao: BinDao,
    private val skuDao: SkuDao,
    private val movementDao: StockMovementDao,
    private val repository: InventoryRepository
) : ViewModel() {

    private val _uiState = MutableStateFlow(ReportsUiState())
    val uiState: StateFlow<ReportsUiState> = _uiState.asStateFlow()

    fun clearMessage() {
        _uiState.update { it.copy(message = null) }
    }

    fun clearError() {
        _uiState.update { it.copy(error = null) }
    }

    fun exportInventory() {
        viewModelScope.launch {
            _uiState.update { it.copy(isExporting = true, error = null) }
            try {
                val file = withContext(Dispatchers.IO) { buildInventoryExcel() }
                shareFile(file)
                _uiState.update {
                    it.copy(isExporting = false, message = "✓ Inventory exported: ${file.name}")
                }
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(isExporting = false, error = "Export failed: ${e.message}")
                }
            }
        }
    }

    fun exportMovements() {
        viewModelScope.launch {
            _uiState.update { it.copy(isExporting = true, error = null) }
            try {
                val file = withContext(Dispatchers.IO) { buildMovementsExcel() }
                shareFile(file)
                _uiState.update {
                    it.copy(isExporting = false, message = "✓ Movements exported: ${file.name}")
                }
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(isExporting = false, error = "Export failed: ${e.message}")
                }
            }
        }
    }

    fun importBins(uri: Uri) {
        viewModelScope.launch {
            _uiState.update { it.copy(isImporting = true, error = null) }
            try {
                val count = withContext(Dispatchers.IO) { readBinsFromExcel(uri) }
                _uiState.update {
                    it.copy(isImporting = false, message = "✓ Imported $count bins")
                }
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(isImporting = false, error = "Import failed: ${e.message}")
                }
            }
        }
    }

    fun importSkus(uri: Uri) {
        viewModelScope.launch {
            _uiState.update { it.copy(isImporting = true, error = null) }
            try {
                val count = withContext(Dispatchers.IO) { readSkusFromExcel(uri) }
                _uiState.update {
                    it.copy(isImporting = false, message = "✓ Imported $count SKUs")
                }
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(isImporting = false, error = "Import failed: ${e.message}")
                }
            }
        }
    }

    // ---- Export helpers ----

    private suspend fun buildInventoryExcel(): File {
        val inventory = inventoryDao.all()
        val wb = XSSFWorkbook()
        val headerStyle = wb.createHeaderStyle()

        val sheet = wb.createSheet("Inventory")
        val headers = listOf("BIN Code", "SKU Code", "Quantity", "Last Updated", "Sync Status")
        val headerRow = sheet.createRow(0)
        headers.forEachIndexed { i, h ->
            headerRow.createCell(i).apply {
                setCellValue(h)
                cellStyle = headerStyle
            }
        }

        val dateFmt = SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.US)
        inventory.forEachIndexed { i, inv ->
            val row = sheet.createRow(i + 1)
            row.createCell(0).setCellValue(inv.binCode)
            row.createCell(1).setCellValue(inv.skuCode)
            row.createCell(2).setCellValue(inv.quantity.toDouble())
            row.createCell(3).setCellValue(dateFmt.format(Date(inv.updatedAt)))
            row.createCell(4).setCellValue(inv.syncStatus)
        }

        headers.indices.forEach { sheet.autoSizeColumn(it) }

        val file = exportFile("inventory")
        file.outputStream().use { wb.write(it) }
        wb.close()
        return file
    }

    private suspend fun buildMovementsExcel(): File {
        val movements = movementDao.observeRecent(5000).first()
        val wb = XSSFWorkbook()
        val headerStyle = wb.createHeaderStyle()

        val sheet = wb.createSheet("Stock Movements")
        val headers = listOf(
            "ID", "Type", "SKU Code", "From BIN", "To BIN",
            "Quantity", "Performed By", "Note", "Created At", "Sync Status"
        )
        val headerRow = sheet.createRow(0)
        headers.forEachIndexed { i, h ->
            headerRow.createCell(i).apply {
                setCellValue(h)
                cellStyle = headerStyle
            }
        }

        val dateFmt = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US)
        movements.forEachIndexed { i, mv ->
            val row = sheet.createRow(i + 1)
            row.createCell(0).setCellValue(mv.id)
            row.createCell(1).setCellValue(mv.type)
            row.createCell(2).setCellValue(mv.skuCode)
            row.createCell(3).setCellValue(mv.fromBinCode ?: "")
            row.createCell(4).setCellValue(mv.toBinCode ?: "")
            row.createCell(5).setCellValue(mv.quantity.toDouble())
            row.createCell(6).setCellValue(mv.performedBy)
            row.createCell(7).setCellValue(mv.note ?: "")
            row.createCell(8).setCellValue(dateFmt.format(Date(mv.createdAt)))
            row.createCell(9).setCellValue(mv.syncStatus)
        }

        headers.indices.forEach { sheet.autoSizeColumn(it) }

        val file = exportFile("movements")
        file.outputStream().use { wb.write(it) }
        wb.close()
        return file
    }

    // ---- Import helpers ----

    private suspend fun readBinsFromExcel(uri: Uri): Int {
        val inputStream = context.contentResolver.openInputStream(uri)
            ?: throw IllegalStateException("Cannot open file")
        val wb = XSSFWorkbook(inputStream)
        val sheet = wb.getSheetAt(0)
        var count = 0

        for (i in 1..sheet.lastRowNum) {
            val row = sheet.getRow(i) ?: continue
            val code = row.getCell(0)?.stringCellValue?.trim() ?: continue
            if (code.isBlank()) continue
            val desc = row.getCell(1)?.stringCellValue?.trim()
            val zone = row.getCell(2)?.stringCellValue?.trim()
            repository.ensureBin(code, desc)
            count++
        }
        wb.close()
        inputStream.close()
        return count
    }

    private suspend fun readSkusFromExcel(uri: Uri): Int {
        val inputStream = context.contentResolver.openInputStream(uri)
            ?: throw IllegalStateException("Cannot open file")
        val wb = XSSFWorkbook(inputStream)
        val sheet = wb.getSheetAt(0)
        var count = 0

        for (i in 1..sheet.lastRowNum) {
            val row = sheet.getRow(i) ?: continue
            val code = row.getCell(0)?.stringCellValue?.trim() ?: continue
            if (code.isBlank()) continue
            val name = row.getCell(1)?.stringCellValue?.trim()
            repository.ensureSku(code, name)
            count++
        }
        wb.close()
        inputStream.close()
        return count
    }

    // ---- Utilities ----

    private fun exportFile(prefix: String): File {
        val dir = File(context.filesDir, "exports").apply { mkdirs() }
        val ts = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(Date())
        return File(dir, "${prefix}_$ts.xlsx")
    }

    private fun shareFile(file: File) {
        val uri = FileProvider.getUriForFile(
            context,
            "${context.packageName}.fileprovider",
            file
        )
        val intent = Intent(Intent.ACTION_SEND).apply {
            type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            putExtra(Intent.EXTRA_STREAM, uri)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        context.startActivity(Intent.createChooser(intent, "Share report").apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        })
    }

    private fun XSSFWorkbook.createHeaderStyle() = createCellStyle().apply {
        fillForegroundColor = IndexedColors.DARK_BLUE.index
        fillPattern = FillPatternType.SOLID_FOREGROUND
        alignment = HorizontalAlignment.CENTER
        val font = createFont().apply {
            bold = true
            color = IndexedColors.WHITE.index
            fontHeightInPoints = 11
        }
        setFont(font)
    }
}
