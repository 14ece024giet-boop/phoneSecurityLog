package com.securityphon.data

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "activity_events")
data class EventEntity(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0,
    val eventType: String,
    val timestamp: String,
    val batteryLevel: Int? = null,
    val latitude: Double? = null,
    val longitude: Double? = null,
    val detailsJson: String = "{}"
)

