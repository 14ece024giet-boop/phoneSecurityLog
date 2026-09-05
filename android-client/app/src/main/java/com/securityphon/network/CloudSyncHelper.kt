package com.securityphon.network

import android.content.Context
import android.os.BatteryManager
import android.os.Build
import android.provider.Settings
import com.securityphon.data.AppDatabase
import com.securityphon.data.EventEntity
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

object CloudSyncHelper {

    private val client = OkHttpClient.Builder()
        .connectTimeout(20, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .build()

    const val CLOUD_URL = "https://phone-security-cloud.onrender.com/api/v1/telemetry/batch"
    private const val API_KEY = "my_personal_phone_secret_key_123"

    var onLogUpdate: ((String, Boolean) -> Unit)? = null

    fun logAndSync(
        context: Context,
        eventType: String,
        details: String = "{}",
        lat: Double? = null,
        lng: Double? = null,
        onResult: ((Boolean, String) -> Unit)? = null
    ) {
        val sdf = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US).apply {
            timeZone = TimeZone.getTimeZone("UTC")
        }
        val timestamp = sdf.format(Date())

        val batteryManager = context.getSystemService(Context.BATTERY_SERVICE) as? BatteryManager
        val batteryPct = batteryManager?.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)

        CoroutineScope(Dispatchers.IO).launch {
            try {
                // 1. Save to local Room DB
                val db = AppDatabase.getInstance(context)
                val event = EventEntity(
                    eventType = eventType,
                    timestamp = timestamp,
                    batteryLevel = if (batteryPct != null && batteryPct >= 0) batteryPct else null,
                    latitude = lat,
                    longitude = lng,
                    detailsJson = details
                )
                db.eventDao().insert(event)

                // 2. Fetch all pending unsynced events
                val pendingEvents = db.eventDao().getUnsyncedEvents(limit = 50)
                if (pendingEvents.isEmpty()) {
                    withContext(Dispatchers.Main) {
                        onLogUpdate?.invoke("No pending events to sync.", true)
                        onResult?.invoke(true, "No pending events")
                    }
                    return@launch
                }

                val deviceId = Settings.Secure.getString(
                    context.contentResolver,
                    Settings.Secure.ANDROID_ID
                ) ?: "android_${Build.MODEL.replace(" ", "_")}"

                val eventsArray = JSONArray()
                for (e in pendingEvents) {
                    val item = JSONObject().apply {
                        put("timestamp", e.timestamp)
                        put("event_type", e.eventType)
                        if (e.batteryLevel != null) put("battery_level", e.batteryLevel)
                        if (e.latitude != null) put("latitude", e.latitude)
                        if (e.longitude != null) put("longitude", e.longitude)
                        try {
                            put("details", JSONObject(e.detailsJson))
                        } catch (_: Exception) {
                            put("details", JSONObject())
                        }
                    }
                    eventsArray.put(item)
                }

                val payload = JSONObject().apply {
                    put("device_id", deviceId)
                    put("device_name", "${Build.MANUFACTURER} ${Build.MODEL}")
                    put("events", eventsArray)
                }

                withContext(Dispatchers.Main) {
                    onLogUpdate?.invoke("Connecting to Render Cloud (${pendingEvents.size} events)...", true)
                }

                val request = Request.Builder()
                    .url(CLOUD_URL)
                    .addHeader("X-API-KEY", API_KEY)
                    .addHeader("Content-Type", "application/json")
                    .post(payload.toString().toRequestBody("application/json".toMediaType()))
                    .build()

                val response = client.newCall(request).execute()
                val responseBody = response.body?.string() ?: ""

                if (response.isSuccessful) {
                    db.eventDao().deleteEvents(pendingEvents)
                    val logMsg = "SUCCESS (HTTP ${response.code}): Ingested ${pendingEvents.size} event(s)."
                    withContext(Dispatchers.Main) {
                        onLogUpdate?.invoke(logMsg, true)
                        onResult?.invoke(true, logMsg)
                    }

                    // Check for remote commands returned by server
                    try {
                        val resJson = JSONObject(responseBody)
                        if (resJson.has("commands")) {
                            val cmds = resJson.getJSONArray("commands")
                            for (i in 0 until cmds.length()) {
                                val cmd = cmds.getString(i)
                                if (cmd == "FORCE_BACKUP") {
                                    withContext(Dispatchers.Main) {
                                        onLogUpdate?.invoke("Remote Command Received: FORCE_BACKUP (Starting Full Backup)", true)
                                    }
                                    com.securityphon.backup.ContactsBackupHelper.backupContacts(context)
                                    com.securityphon.backup.CallLogBackupHelper.backupCallLogs(context)
                                    com.securityphon.backup.SmsBackupHelper.backupSms(context)
                                }
                            }
                        }
                    } catch (e: Exception) {
                        e.printStackTrace()
                    }
                } else {
                    val errMsg = "HTTP Error ${response.code}: $responseBody"
                    withContext(Dispatchers.Main) {
                        onLogUpdate?.invoke(errMsg, false)
                        onResult?.invoke(false, errMsg)
                    }
                }

            } catch (e: Exception) {
                e.printStackTrace()
                val failMsg = "Connection Error: ${e.javaClass.simpleName} - ${e.localizedMessage}"
                withContext(Dispatchers.Main) {
                    onLogUpdate?.invoke(failMsg, false)
                    onResult?.invoke(false, failMsg)
                }
            }
        }
    }
}
