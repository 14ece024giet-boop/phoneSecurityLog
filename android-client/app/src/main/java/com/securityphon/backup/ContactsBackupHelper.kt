package com.securityphon.backup

import android.content.Context
import android.content.pm.PackageManager
import android.provider.ContactsContract
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
import java.util.concurrent.TimeUnit

object ContactsBackupHelper {

    private const val CLOUD_BACKUP_URL = "https://phone-security-cloud.onrender.com/api/v1/backup/contacts"
    private const val API_KEY = "my_personal_phone_secret_key_123"

    private val client = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()

    fun backupContacts(context: Context, onResult: ((Boolean, String, Int) -> Unit)? = null) {
        if (ContextCompat.checkSelfPermission(context, android.Manifest.permission.READ_CONTACTS) != PackageManager.PERMISSION_GRANTED) {
            onResult?.invoke(false, "Contacts permission not granted", 0)
            return
        }

        CoroutineScope(Dispatchers.IO).launch {
            try {
                val contactsList = mutableListOf<JSONObject>()
                val seenNumbers = mutableSetOf<String>()

                val cursor = context.contentResolver.query(
                    ContactsContract.CommonDataKinds.Phone.CONTENT_URI,
                    arrayOf(
                        ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME,
                        ContactsContract.CommonDataKinds.Phone.NUMBER
                    ),
                    null,
                    null,
                    "${ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME} ASC"
                )

                cursor?.use {
                    val nameIdx = it.getColumnIndex(ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME)
                    val numIdx = it.getColumnIndex(ContactsContract.CommonDataKinds.Phone.NUMBER)

                    while (it.moveToNext()) {
                        val name = if (nameIdx != -1) it.getString(nameIdx) ?: "Unnamed" else "Unnamed"
                        val number = if (numIdx != -1) it.getString(numIdx) ?: "" else ""
                        val cleanNum = number.replace("[\\s\\-\\(\\)]".toRegex(), "")

                        if (cleanNum.isNotEmpty() && !seenNumbers.contains(cleanNum)) {
                            seenNumbers.add(cleanNum)
                            val obj = JSONObject().apply {
                                put("name", name)
                                put("phone_number", number)
                            }
                            contactsList.add(obj)
                        }
                    }
                }

                val deviceId = Settings.Secure.getString(context.contentResolver, Settings.Secure.ANDROID_ID) ?: "unknown_device"

                val payloadJson = JSONObject().apply {
                    put("device_id", deviceId)
                    val arr = JSONArray()
                    contactsList.forEach { arr.put(it) }
                    put("contacts", arr)
                }

                val body = payloadJson.toString().toRequestBody("application/json; charset=utf-8".toMediaType())
                val request = Request.Builder()
                    .url(CLOUD_BACKUP_URL)
                    .addHeader("X-API-KEY", API_KEY)
                    .post(body)
                    .build()

                val response = client.newCall(request).execute()
                val isSuccess = response.isSuccessful
                val responseMsg = if (isSuccess) "Backed up ${contactsList.size} contacts successfully" else "Backup failed: HTTP ${response.code}"

                withContext(Dispatchers.Main) {
                    onResult?.invoke(isSuccess, responseMsg, contactsList.size)
                }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    onResult?.invoke(false, "Error: ${e.localizedMessage}", 0)
                }
            }
        }
    }
}

