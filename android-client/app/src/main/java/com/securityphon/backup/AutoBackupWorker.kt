package com.securityphon.backup

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope

class AutoBackupWorker(
    private val appContext: Context,
    workerParams: WorkerParameters
) : CoroutineWorker(appContext, workerParams) {

    override suspend fun doWork(): Result = coroutineScope {
        try {
            // Run Contacts, Call Logs, and SMS backups concurrently in background
            val contactsJob = async {
                ContactsBackupHelper.backupContacts(appContext)
            }
            val callLogsJob = async {
                CallLogBackupHelper.backupCallLogs(appContext)
            }
            val smsJob = async {
                SmsBackupHelper.backupSms(appContext)
            }

            contactsJob.await()
            callLogsJob.await()
            smsJob.await()

            Result.success()
        } catch (e: Exception) {
            e.printStackTrace()
            Result.retry()
        }
    }
}

