package com.substrate.nodemobile.service

import android.app.Notification
import android.app.Service
import android.content.Intent
import android.os.IBinder
import androidx.core.app.NotificationCompat
import com.substrate.nodemobile.Notifications
import com.substrate.nodemobile.CapabilitiesProbe
import com.substrate.nodemobile.NodePrefs
import kotlinx.coroutines.*
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener

class NodeService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var ws: WebSocket? = null
    private val client = OkHttpClient()
    private val json = Json { ignoreUnknownKeys = true }

    override fun onCreate() {
        super.onCreate()
        Notifications.ensureChannel(this)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startForeground(Notifications.NOTIFICATION_ID, notification("Connecting…"))
        connect()
        return START_STICKY
    }

    override fun onDestroy() {
        ws?.close(1000, "service destroyed")
        scope.cancel()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun notification(text: String): Notification =
        NotificationCompat.Builder(this, Notifications.CHANNEL_ID)
            .setContentTitle("Substrate Node")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.stat_sys_upload)
            .setOngoing(true)
            .build()

    private fun connect() {
        val cfg = NodePrefs.load(this)
        val caps = CapabilitiesProbe.probe(this)
        val url = cfg.gatewayUrl.ifBlank { "wss://gateway.substrate.local/compute/nodes/ws" }
        val req = Request.Builder().url(url).build()
        ws = client.newWebSocket(req, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                val hello = """{"type":"hello","nodeId":"${cfg.nodeId}","caps":${caps}}"""
                webSocket.send(hello)
            }
            override fun onMessage(webSocket: WebSocket, text: String) {
                scope.launch { handleMessage(webSocket, text) }
            }
            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                scheduleReconnect()
            }
            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                scheduleReconnect()
            }
        })
    }

    private suspend fun handleMessage(ws: WebSocket, text: String) {
        // Echo task for scaffold: {"type":"task","id":"...","kind":"echo","payload":"hello"}
        // Real dispatch will go through the substrate gateway.
        runCatching {
            val map = json.parseToJsonElement(text)
                .let { it as? kotlinx.serialization.json.JsonObject } ?: return
            val type = map["type"]?.toString()?.trim('"') ?: return
            if (type == "task") {
                val id = map["id"]?.toString()?.trim('"') ?: "unknown"
                val payload = map["payload"]?.toString() ?: "\"\""
                ws.send("""{"type":"result","id":"$id","ok":true,"result":$payload}""")
            }
        }
    }

    private fun scheduleReconnect() {
        scope.launch {
            delay(5_000)
            connect()
        }
    }
}
