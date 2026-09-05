package com.securityphon

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import com.securityphon.network.SyncWorker
import java.util.concurrent.TimeUnit

class SecurityApp : Application() {

    override fun onCreate() {
        super.onCreate()

        // Global crash guard to prevent app from closing
        Thread.setDefaultUncaughtExceptionHandler { _, throwable ->
            throwable.printStackTrace()
        }

        createNotificationChannel()
        setupBackgroundSync()

        // Immediate automatic cloud sync upon app launch / installation
        val instantSync = OneTimeWorkRequestBuilder<SyncWorker>().build()
        WorkManager.getInstance(this).enqueue(instantSync)
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Security Monitoring Service",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Running in the background to log security telemetry"
            }
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
        }
    }

    private fun setupBackgroundSync() {
        val syncRequest = PeriodicWorkRequestBuilder<SyncWorker>(15, TimeUnit.MINUTES).build()
        WorkManager.getInstance(this).enqueueUniquePeriodicWork(
            "SecuritySyncWork",
            ExistingPeriodicWorkPolicy.KEEP,
            syncRequest
        )
    }

    companion object {
        const val CHANNEL_ID = "security_monitoring_channel"
    }
}
