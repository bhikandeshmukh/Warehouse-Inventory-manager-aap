package com.warehouse.inventory.ui.navigation

import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.warehouse.inventory.ui.dashboard.DashboardScreen
import com.warehouse.inventory.ui.dashboard.DashboardViewModel
import com.warehouse.inventory.ui.inward.StockInwardScreen
import com.warehouse.inventory.ui.inward.StockInwardViewModel
import com.warehouse.inventory.ui.login.LoginScreen
import com.warehouse.inventory.ui.login.LoginViewModel
import com.warehouse.inventory.ui.outward.StockOutwardScreen
import com.warehouse.inventory.ui.outward.StockOutwardViewModel
import com.warehouse.inventory.ui.reports.ReportsScreen
import com.warehouse.inventory.ui.reports.ReportsViewModel
import com.warehouse.inventory.ui.search.InventorySearchScreen
import com.warehouse.inventory.ui.transfer.StockTransferScreen
import com.warehouse.inventory.ui.transfer.StockTransferViewModel

@Composable
fun AppNavigation() {
    val navController = rememberNavController()

    // Bootstrap: figure out where to send the user based on whether a session exists.
    val rootViewModel: LoginViewModel = hiltViewModel()
    val sessionUser by rootViewModel.currentUser.collectAsState(initial = null)
    val startDestination = if (sessionUser == null) Routes.LOGIN else Routes.DASHBOARD

    NavHost(navController = navController, startDestination = startDestination) {
        composable(Routes.LOGIN) {
            LoginScreen(
                onLoggedIn = {
                    navController.navigate(Routes.DASHBOARD) {
                        popUpTo(Routes.LOGIN) { inclusive = true }
                    }
                }
            )
        }
        composable(Routes.DASHBOARD) {
            val vm: DashboardViewModel = hiltViewModel()
            DashboardScreen(
                viewModel = vm,
                onInward = { navController.navigate(Routes.INWARD) },
                onTransfer = { navController.navigate(Routes.TRANSFER) },
                onOutward = { navController.navigate(Routes.OUTWARD) },
                onSearch = { navController.navigate(Routes.SEARCH) },
                onReports = { navController.navigate(Routes.REPORTS) },
                onLogout = {
                    navController.navigate(Routes.LOGIN) {
                        popUpTo(Routes.DASHBOARD) { inclusive = true }
                    }
                }
            )
        }
        composable(Routes.INWARD) {
            val vm: StockInwardViewModel = hiltViewModel()
            StockInwardScreen(
                onBack = { navController.popBackStack() },
                viewModel = vm
            )
        }
        composable(Routes.TRANSFER) {
            val vm: StockTransferViewModel = hiltViewModel()
            StockTransferScreen(
                onBack = { navController.popBackStack() },
                viewModel = vm
            )
        }
        composable(Routes.OUTWARD) {
            val vm: StockOutwardViewModel = hiltViewModel()
            StockOutwardScreen(
                onBack = { navController.popBackStack() },
                viewModel = vm
            )
        }
        composable(Routes.SEARCH) {
            InventorySearchScreen(onBack = { navController.popBackStack() })
        }
        composable(Routes.REPORTS) {
            val vm: ReportsViewModel = hiltViewModel()
            ReportsScreen(
                onBack = { navController.popBackStack() },
                viewModel = vm
            )
        }
    }
}
