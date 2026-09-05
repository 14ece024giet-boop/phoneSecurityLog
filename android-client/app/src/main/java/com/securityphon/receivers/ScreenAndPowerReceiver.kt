package com.securityphon.receivers

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.securityphon.network.CloudSyncHelper

class ScreenAndPowerReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        val action = intent.action ?: return

        val eventType = when (action) {
            Intent.ACTION_USER_PRESENT -> "SCREEN_UNLOCK"
            Intent.ACTION_SCREEN_ON -> "SCREEN_ON"
            Intent.ACTION_SCREEN_OFF -> "SCREEN_OFF"
            Intent.ACTION_POWER_CONNECTED -> "CHARGING_CONNECTED"
            Intent.ACTION_POWER_DISCONNECTED -> "CHARGING_DISCONNECTED"
            Intent.ACTION_BOOT_COMPLETED -> "DEVICE_BOOTED"
            else -> action
        }

        // Direct instant cloud upload on every broadcast event
        CloudSyncHelper.logAndSync(
            context = context,
            eventType = eventType,
            details = "{\"action\": \"$action\"}"
        )
    }
}
