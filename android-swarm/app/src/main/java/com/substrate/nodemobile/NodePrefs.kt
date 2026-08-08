package com.substrate.nodemobile

import android.content.Context
import android.os.Build
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

@Serializable
data class NodeConfig(
    val gatewayUrl: String = "wss://gateway.substrate.local/compute/nodes/ws",
    val nodeId: String = "",
    val displayName: String = Build.MODEL
)

object NodePrefs {
    private const val FILE = "substrate_node"
    private const val KEY = "config"
    private val json = Json { ignoreUnknownKeys = true }

    fun load(ctx: Context): NodeConfig {
        val raw = ctx.getSharedPreferences(FILE, Context.MODE_PRIVATE).getString(KEY, null)
            ?: return NodeConfig()
        return runCatching { json.decodeFromString<NodeConfig>(raw) }.getOrDefault(NodeConfig())
    }

    fun save(ctx: Context, cfg: NodeConfig) {
        ctx.getSharedPreferences(FILE, Context.MODE_PRIVATE).edit()
            .putString(KEY, json.encodeToString(cfg)).apply()
    }
}
