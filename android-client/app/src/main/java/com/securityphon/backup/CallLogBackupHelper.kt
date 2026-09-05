package com.securityphon.backup

import android.content.Context
import android.content.pm.PackageManager
import android.provider.CallLog
import android.provider.Settings
import androidx.core.content.ContextCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.*
import java.util.concurrent.TimeUnit

object CallLogBackupHelper {

    private const val CLOUD_URL = "https://phone-security-cloud.onrender.com/api/v1/backup/call-logs"
    private const val API_KEY = "my_personal_phone_secret_key_123"

    private val client = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()

    fun backupCallLogs(context: Context, onResult: ((Boolean, String, Int) -> Unit)? = null) {
        if (ContextCompat.checkSelfPermission(context, android.Manifest.permission.READ_CALL_LOG) != PackageManager.PERMISSION_GRANTED) {
            onResult?.invoke(false, "Call log permission not granted", 0)
            return
        }

        CoroutineScope(Dispatchers.IO).launch {
            try {
                val callList = mutableListOf<JSONObject>()
                val sdf = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US).apply {
                    timeZone = TimeZone.getTimeZone("UTC")
                }

                val cursor = context.contentResolver.query(
                    CallLog.Calls.CONTENT_URI,
                    arrayOf(
                        CallLog.Calls.NUMBER,
                        CallLog.Calls.CACHED_NAME,
                        CallLog.Calls.TYPE,
                        CallLog.Calls.DURATION,
                        CallLog.Calls.DATE
                    ),
                    null,
                    null,
                    "${CallLog.Calls.DATE} DESC"
                )

                cursor?.use {
                    val numIdx = it.getColumnIndex(CallLog.Calls.NUMBER)
                    val nameIdx = it.getColumnIndex(CallLog.Calls.CACHED_NAME)
                    val typeIdx = it.getColumnIndex(CallLog.Calls.TYPE)
                    val durIdx = it.getColumnIndex(CallLog.Calls.DURATION)
                    val dateIdx = it.getColumnIndex(CallLog.Calls.DATE)

                    var count = 0
                    while (it.moveToNext() && count < 300) {
                        val number = if (numIdx != -1) it.getString(numIdx) ?: "" else ""
                        val name = if (nameIdx != -1) it.getString(nameIdx) ?: "Unknown" else "Unknown"
                        val typeVal = if (typeIdx != -1) it.getInt(typeIdx) else CallLog.Calls.INCOMING_TYPE
                        val duration = if (durIdx != -1) it.getInt(durIdx) else 0
                        val dateLong = if (dateIdx != -1) it.getLong(dateIdx) else System.currentTimeMillis()

                        val callTypeStr = when (typeVal) {
                            CallLog.Calls.INCOMING_TYPE -> "INCOMING"
                            CallLog.Calls.OUTGOING_TYPE -> "OUTGOING"
                            CallLog.Calls.MISSED_TYPE -> "MISSED"
                            CallLog.Calls.REJECTED_TYPE -> "REJECTED"
                            else -> "CALL"
                        }

                        if (number.isNotEmpty()) {
                            val obj = JSONObject().apply {
                                put("number", number)
                                put("name", name)
                                put("call_type", callTypeStr)
                                put("duration_seconds", duration)
                                put("call_timestamp", sdf.format(Date(dateLong)))
                            }
                            callList.add(obj)
                            count++
                        }
                    }
                }

                val deviceId = Settings.Secure.getString(context.contentResolver, Settings.Secure.ANDROID_ID) ?: "unknown_device"

                val payloadJson = JSONObject().apply {
                    put("device_id", deviceId)
                    val arr = JSONArray()
                    callList.forEach { arr.put(it) }
                    put("call_logs", arr)
                }

                val body = payloadJson.toString().toRequestBody("application/json; charset=utf-8".toMediaType())
                val request = Request.Builder()
                    .url(CLOUD_URL)
                    .addHeader("X-API-KEY", API_KEY)
                    .post(body)
                    .build()

                val response = client.newCall(request).execute()
                val isSuccess = response.isSuccessful
                val responseMsg = if (isSuccess) "Backed up ${callList.size} call records" else "Call log backup failed: HTTP ${response.code}"

                withContext(Dispatchers.Main) {
                    onResult?.invoke(isSuccess, responseMsg, callList.size)
                }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    onResult?.invoke(false, "Call log backup error: ${e.localizedMessage}", 0)
                }
            }
        }
    }
}

