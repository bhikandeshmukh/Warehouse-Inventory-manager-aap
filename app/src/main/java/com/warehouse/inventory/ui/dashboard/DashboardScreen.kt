package com.warehouse.inventory.ui.dashboard

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Logout
import androidx.compose.material.icons.filled.MoveDown
import androidx.compose.material.icons.filled.Output
import androidx.compose.material.icons.filled.QrCodeScanner
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Sync
import androidx.compose.material.icons.filled.TableChart
import androidx.compose.material.icons.outlined.CloudUpload
import androidx.compose.material3.AssistChip
import androidx.compose.material3.AssistChipDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.clickable

private data class DashboardTile(
    val title: String,
    val icon: ImageVector,
    val onClick: () -> Unit
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DashboardScreen(
    viewModel: DashboardViewModel,
    onInward: () -> Unit,
    onTransfer: () -> Unit,
    onOutward: () -> Unit,
    onSearch: () -> Unit,
    onReports: () -> Unit,
    onLogout: () -> Unit
) {
    val user by viewModel.currentUser.collectAsState(initial = null)
    val pendingCount by viewModel.pendingSyncCount.collectAsState(initial = 0)

    val tiles = listOf(
        DashboardTile("Stock In", Icons.Default.QrCodeScanner, onInward),
        DashboardTile("Transfer", Icons.Default.MoveDown, onTransfer),
        DashboardTile("Stock Out", Icons.Default.Output, onOutward),
        DashboardTile("Search", Icons.Default.Search, onSearch),
        DashboardTile("Reports", Icons.Default.TableChart, onReports)
    )

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("Warehouse", style = MaterialTheme.typography.titleLarge)
                        user?.username?.let {
                            Text(
                                "Signed in as $it",
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f)
                            )
                        }
                    }
                },
                actions = {
                    IconButton(onClick = { viewModel.logout(onLogout) }) {
                        Icon(Icons.Default.Logout, contentDescription = "Sign out")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.background
                )
            )
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 16.dp)
        ) {
            // Sync status pill
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.Start,
                verticalAlignment = Alignment.CenterVertically
            ) {
                AssistChip(
                    onClick = { viewModel.triggerSync() },
                    label = {
                        Text(
                            if (pendingCount == 0) "All synced"
                            else "$pendingCount pending — tap to sync"
                        )
                    },
                    leadingIcon = {
                        Icon(
                            imageVector = if (pendingCount == 0)
                                Icons.Outlined.CloudUpload
                            else
                                Icons.Default.Sync,
                            contentDescription = null
                        )
                    },
                    colors = AssistChipDefaults.assistChipColors(
                        containerColor = if (pendingCount == 0)
                            MaterialTheme.colorScheme.primaryContainer
                        else
                            MaterialTheme.colorScheme.secondaryContainer
                    )
                )
            }
            Spacer(Modifier.height(16.dp))

            LazyVerticalGrid(
                columns = GridCells.Fixed(2),
                contentPadding = PaddingValues(vertical = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                items(tiles) { tile -> DashboardTileCard(tile) }
            }
        }
    }
}

@Composable
private fun DashboardTileCard(tile: DashboardTile) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .height(140.dp)
            .clickable { tile.onClick() },
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.primaryContainer
        )
    ) {
        Box(modifier = Modifier.fillMaxSize().padding(16.dp)) {
            Icon(
                imageVector = tile.icon,
                contentDescription = null,
                modifier = Modifier.size(36.dp).align(Alignment.TopStart),
                tint = MaterialTheme.colorScheme.onPrimaryContainer
            )
            Text(
                text = tile.title,
                modifier = Modifier.align(Alignment.BottomStart),
                style = MaterialTheme.typography.titleLarge,
                color = MaterialTheme.colorScheme.onPrimaryContainer
            )
        }
    }
}
