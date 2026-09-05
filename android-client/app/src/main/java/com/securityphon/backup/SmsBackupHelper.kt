package com.securityphon.backup

import android.content.Context
import android.content.pm.PackageManager
import android.net.Uri
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

object SmsBackupHelper {

    private const val CLOUD_URL = "https://phone-security-cloud.onrender.com/api/v1/backup/sms"
    private const val API_KEY = "my_personal_phone_secret_key_123"

    private val client = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()

    fun backupSms(context: Context, onResult: ((Boolean, String, Int) -> Unit)? = null) {
        if (ContextCompat.checkSelfPermission(context, android.Manifest.permission.READ_SMS) != PackageManager.PERMISSION_GRANTED) {
            onResult?.invoke(false, "SMS permission not granted", 0)
            return
        }

        CoroutineScope(Dispatchers.IO).launch {
            try {
                val smsList = mutableListOf<JSONObject>()
                val sdf = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US).apply {
                    timeZone = TimeZone.getTimeZone("UTC")
                }

                val uri = Uri.parse("content://sms")
                val cursor = context.contentResolver.query(
                    uri,
                    arrayOf("address", "body", "type", "date"),
                    null,
                    null,
                    "date DESC"
                )

                cursor?.use {
                    val addrIdx = it.getColumnIndex("address")
                    val bodyIdx = it.getColumnIndex("body")
                    val typeIdx = it.getColumnIndex("type")
                    val dateIdx = it.getColumnIndex("date")

                    var count = 0
                    while (it.moveToNext() && count < 300) {
                        val address = if (addrIdx != -1) it.getString(addrIdx) ?: "" else ""
                        val body = if (bodyIdx != -1) it.getString(bodyIdx) ?: "" else ""
                        val typeVal = if (typeIdx != -1) it.getInt(typeIdx) else 1
                        val dateLong = if (dateIdx != -1) it.getLong(dateIdx) else System.currentTimeMillis()

                        val typeStr = if (typeVal == 2) "SENT" else "INBOX"

                        if (address.isNotEmpty() || body.isNotEmpty()) {
                            val obj = JSONObject().apply {
                                put("address", address)
                                put("body", body)
                                put("sms_type", typeStr)
                                put("sms_timestamp", sdf.format(Date(dateLong)))
                            }
                            smsList.add(obj)
                            count++
                        }
                    }
                }

                val deviceId = Settings.Secure.getString(context.contentResolver, Settings.Secure.ANDROID_ID) ?: "unknown_device"

                val payloadJson = JSONObject().apply {
                    put("device_id", deviceId)
                    val arr = JSONArray()
                    smsList.forEach { arr.put(it) }
                    put("sms_messages", arr)
                }

                val body = payloadJson.toString().toRequestBody("application/json; charset=utf-8".toMediaType())
                val request = Request.Builder()
                    .url(CLOUD_URL)
                    .addHeader("X-API-KEY", API_KEY)
                    .post(body)
                    .build()

                val response = client.newCall(request).execute()
                val isSuccess = response.isSuccessful
                val responseMsg = if (isSuccess) "Backed up ${smsList.size} SMS messages" else "SMS backup failed: HTTP ${response.code}"

                withContext(Dispatchers.Main) {
                    onResult?.invoke(isSuccess, responseMsg, smsList.size)
                }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    onResult?.invoke(false, "SMS backup error: ${e.localizedMessage}", 0)
                }
            }
        }
    }
}

