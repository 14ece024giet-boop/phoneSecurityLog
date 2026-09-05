package com.securityphon.data

import androidx.room.Dao
import androidx.room.Delete
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query

@Dao
interface EventDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(event: EventEntity): Long

    @Query("SELECT * FROM activity_events ORDER BY id ASC LIMIT :limit")
    suspend fun getUnsyncedEvents(limit: Int = 50): List<EventEntity>

    @Delete
    suspend fun deleteEvents(events: List<EventEntity>)

    @Query("SELECT COUNT(*) FROM activity_events")
    suspend fun getPendingCount(): Int
}

