package com.securityphon.network

import android.content.Context
import android.os.Build
import android.provider.Settings
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.securityphon.data.AppDatabase
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.TimeUnit

class SyncWorker(appContext: Context, workerParams: WorkerParameters) :
    CoroutineWorker(appContext, workerParams) {

    private val client = OkHttpClient.Builder()
        .connectTimeout(20, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .build()

    // Permanent Cloud Render URL
    private val cloudServerUrl = "https://phone-security-cloud.onrender.com/api/v1/telemetry/batch"
    private val apiKey = "my_personal_phone_secret_key_123"

    override suspend fun doWork(): Result {
        val db = AppDatabase.getInstance(applicationContext)
        val pendingEvents = db.eventDao().getUnsyncedEvents(limit = 50)

        if (pendingEvents.isEmpty()) {
            return Result.success()
        }

        val deviceId = Settings.Secure.getString(
            applicationContext.contentResolver,
            Settings.Secure.ANDROID_ID
        ) ?: "android_${Build.MODEL.replace(" ", "_")}"

        val eventsArray = JSONArray()
        for (event in pendingEvents) {
            val item = JSONObject().apply {
                put("timestamp", event.timestamp)
                put("event_type", event.eventType)
                if (event.batteryLevel != null) put("battery_level", event.batteryLevel)
                if (event.latitude != null) put("latitude", event.latitude)
                if (event.longitude != null) put("longitude", event.longitude)
                try {
                    put("details", JSONObject(event.detailsJson))
                } catch (e: Exception) {
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

        val request = Request.Builder()
            .url(cloudServerUrl)
            .addHeader("X-API-KEY", apiKey)
            .addHeader("Content-Type", "application/json")
            .post(payload.toString().toRequestBody("application/json".toMediaType()))
            .build()

        return try {
            val response = client.newCall(request).execute()
            if (response.isSuccessful) {
                db.eventDao().deleteEvents(pendingEvents)
                Result.success()
            } else {
                Result.retry()
            }
        } catch (e: Exception) {
            e.printStackTrace()
            Result.retry()
        }
    }
}
