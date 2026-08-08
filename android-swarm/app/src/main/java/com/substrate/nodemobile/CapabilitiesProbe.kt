package com.substrate.nodemobile

import android.content.Context
import kotlinx.serialization.Serializable

@Serializable
data class Capabilities(
    val cpuCores: Int = Runtime.getRuntime().availableProcessors(),
    val totalRamMb: Long = 0,
    val freeRamMb: Long = 0,
    val storageFreeMb: Long = 0,
    val gpu: String = "unknown",
    val npu: String = "unknown",
    val abi: String = android.os.Build.SUPPORTED_ABIS.firstOrNull() ?: "unknown",
    val androidRelease: String = android.os.Build.VERSION.RELEASE ?: "?",
    val sdkInt: Int = android.os.Build.VERSION.SDK_INT
)

object CapabilitiesProbe {
    fun probe(ctx: Context): Capabilities {
        val am = ctx.getSystemService(Context.ACTIVITY_SERVICE) as android.app.ActivityManager
        val mi = android.app.ActivityManager.MemoryInfo()
        am.getMemoryInfo(mi)
        val stat = android.os.StatFs(android.os.Environment.getDataDirectory().path)
        val freeMb = (stat.availableBlocksLong * stat.blockSizeLong) / (1024 * 1024)
        val gpu = probeVulkan()
        val npu = probeNpu()
        return Capabilities(
            totalRamMb = mi.totalMem / (1024 * 1024),
            freeRamMb = mi.availMem / (1024 * 1024),
            storageFreeMb = freeMb,
            gpu = gpu,
            npu = npu
        )
    }

    private fun probeVulkan(): String = try {
        // Best-effort: existence of Vulkan loader implies GPU compute path is present.
        // A real Vulkan probe will be added in the NDK layer; for now report loader.
        System.loadLibrary("vulkan")
        "vulkan-loader-present"
    } catch (_: Throwable) { "unavailable" }

    private fun probeNpu(): String = try {
        // Reflection so the APK runs on Android < 17 without the new class.
        Class.forName("android.npumanager.NpuManager")
        "npumanager-present"
    } catch (_: ClassNotFoundException) { "nnapi-or-none" }
}
