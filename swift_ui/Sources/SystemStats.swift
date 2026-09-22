import Foundation
import AppKit
import Darwin

struct SystemSnapshot {
    let ramPercentage: Int
    let ramUsedGB: Double
    let ramTotalGB: Double
    let cpuPercentage: Int
    let frontmostApp: String
}

class SystemStats {
    static let shared = SystemStats()
    private var previousCpuInfo = host_cpu_load_info()
    private var hasPrevCpu = false

    func getSnapshot() -> SystemSnapshot {
        // 1. RAM Usage via Mach vm_statistics64
        var vmStats = vm_statistics64()
        var count = mach_msg_type_number_t(MemoryLayout<vm_statistics64>.size / MemoryLayout<integer_t>.size)
        let hostPort = mach_host_self()
        let vmResult = withUnsafeMutablePointer(to: &vmStats) {
            $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                host_statistics64(hostPort, HOST_VM_INFO64, $0, &count)
            }
        }

        var ramPct = 50
        var usedGB = 8.0
        let totalGB = Double(ProcessInfo.processInfo.physicalMemory) / (1024 * 1024 * 1024)

        if vmResult == KERN_SUCCESS {
            let pageSize = UInt64(vm_page_size)
            let active = UInt64(vmStats.active_count) * pageSize
            let wired = UInt64(vmStats.wire_count) * pageSize
            let compressed = UInt64(vmStats.compressor_page_count) * pageSize
            let usedBytes = active + wired + compressed
            usedGB = Double(usedBytes) / (1024 * 1024 * 1024)
            ramPct = Int((usedGB / totalGB) * 100.0)
        }

        // 2. CPU Usage via HOST_CPU_LOAD_INFO
        var cpuPct = 15
        var cpuInfo = host_cpu_load_info()
        var cpuCount = mach_msg_type_number_t(MemoryLayout<host_cpu_load_info>.size / MemoryLayout<integer_t>.size)
        let cpuResult = withUnsafeMutablePointer(to: &cpuInfo) {
            $0.withMemoryRebound(to: integer_t.self, capacity: Int(cpuCount)) {
                host_statistics(hostPort, HOST_CPU_LOAD_INFO, $0, &cpuCount)
            }
        }

        if cpuResult == KERN_SUCCESS {
            if hasPrevCpu {
                let userDiff = Double(cpuInfo.cpu_ticks.0 - previousCpuInfo.cpu_ticks.0)
                let sysDiff = Double(cpuInfo.cpu_ticks.1 - previousCpuInfo.cpu_ticks.1)
                let idleDiff = Double(cpuInfo.cpu_ticks.2 - previousCpuInfo.cpu_ticks.2)
                let niceDiff = Double(cpuInfo.cpu_ticks.3 - previousCpuInfo.cpu_ticks.3)
                let totalDiff = userDiff + sysDiff + idleDiff + niceDiff
                if totalDiff > 0 {
                    cpuPct = max(1, min(100, Int(((userDiff + sysDiff + niceDiff) / totalDiff) * 100.0)))
                }
            }
            previousCpuInfo = cpuInfo
            hasPrevCpu = true
        }

        // 3. Frontmost App
        let frontApp = NSWorkspace.shared.frontmostApplication?.localizedName ?? "Finder"

        return SystemSnapshot(
            ramPercentage: ramPct,
            ramUsedGB: (usedGB * 10).rounded() / 10,
            ramTotalGB: (totalGB * 10).rounded() / 10,
            cpuPercentage: cpuPct,
            frontmostApp: frontApp
        )
    }
}
