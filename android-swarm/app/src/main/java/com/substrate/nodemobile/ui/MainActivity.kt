package com.substrate.nodemobile.ui

import android.content.Intent
import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import com.substrate.nodemobile.CapabilitiesProbe
import com.substrate.nodemobile.databinding.ActivityMainBinding
import com.substrate.nodemobile.service.NodeService

class MainActivity : AppCompatActivity() {
    private lateinit var binding: ActivityMainBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        refreshCapabilities()

        binding.startButton.setOnClickListener {
            startForegroundService(Intent(this, NodeService::class.java))
            binding.statusText.text = "Node running (foreground service)"
        }
        binding.stopButton.setOnClickListener {
            stopService(Intent(this, NodeService::class.java))
            binding.statusText.text = "Node stopped"
        }
    }

    private fun refreshCapabilities() {
        val caps = CapabilitiesProbe.probe(this)
        binding.capabilitiesText.text =
            "CPU cores: ${caps.cpuCores} · RAM: ${caps.freeRamMb}/${caps.totalRamMb} MB · " +
            "Storage free: ${caps.storageFreeMb} MB\n" +
            "GPU: ${caps.gpu} · NPU: ${caps.npu} · ABI: ${caps.abi} · Android ${caps.androidRelease} (SDK ${caps.sdkInt})"
    }
}
