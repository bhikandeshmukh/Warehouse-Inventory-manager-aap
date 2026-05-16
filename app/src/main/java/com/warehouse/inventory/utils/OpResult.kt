package com.warehouse.inventory.utils

/**
 * Lightweight result wrapper. Using a sealed class makes the UI layer handle
 * loading/success/error explicitly without resorting to throwing exceptions
 * across coroutine boundaries.
 */
sealed class OpResult<out T> {
    data object Loading : OpResult<Nothing>()
    data class Success<T>(val data: T) : OpResult<T>()
    data class Error(val message: String, val cause: Throwable? = null) : OpResult<Nothing>()
}
