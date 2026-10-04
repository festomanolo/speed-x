import SwiftUI

struct SystemCard: View {
    @Bindable var model: AppModel

    private var snap: SystemSnapshot { model.snapshot }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            CardHeader(module: .system, subtitle: "Active app · \(model.lastExternalApp ?? snap.frontmostApp)") {
                IconButton(symbol: "xmark", help: "Close") { model.close() }
            }

            HStack(spacing: 8) {
                ResourceRing(title: "CPU", value: snap.cpuPercentage, detail: "\(ProcessInfo.processInfo.activeProcessorCount) threads", tint: Color(red: 0.25, green: 0.7, blue: 1.0))
                ResourceRing(title: "Memory", value: snap.ramPercentage, detail: String(format: "%.1f / %.0f GB", snap.ramUsedGB, snap.ramTotalGB), tint: Module.system.tint)
            }

            CardSection(title: "Microphone") {
                MicrophonePicker(model: model)
            }

            CardSection(title: "Shortcuts") {
                ShortcutRow(keys: "⌥ Space", label: "Talk to Speed-X")
                ShortcutRow(keys: "⌘ ⇧ Space", label: "Type a command")
                ShortcutRow(keys: "esc", label: "Dismiss")
                Divider().opacity(0.4)
                Toggle(isOn: Binding(
                    get: { model.launchAtLogin },
                    set: { model.launchAtLogin = LaunchAtLoginManager.shared.setEnabled($0) }
                )) {
                    Text("Open at login").font(.system(size: 12.5, weight: .medium))
                }
                .toggleStyle(.switch)
                .controlSize(.small)
                .tint(Module.system.tint)
            }
        }
        .padding(16)
    }
}

struct ResourceRing: View {
    let title: String
    let value: Int
    let detail: String
    let tint: Color

    var body: some View {
        HStack(spacing: 10) {
            RingGauge(value: Double(value) / 100, tint: value > 85 ? .red : tint, lineWidth: 4.5) {
                Text("\(value)")
                    .font(.system(size: 13, weight: .bold, design: .rounded))
                    .monospacedDigit()
            }
            .frame(width: 44, height: 44)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.system(size: 12.5, weight: .semibold))
                Text(detail).font(.system(size: 10.5)).foregroundStyle(.secondary).lineLimit(1).minimumScaleFactor(0.8)
            }
            Spacer(minLength: 0)
        }
        .padding(10)
        .frame(maxWidth: .infinity)
        .background(Color.primary.opacity(0.055), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
    }
}

struct MicrophonePicker: View {
    @Bindable var model: AppModel

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack(spacing: 9) {
                Image(systemName: model.selectedDevice?.symbol ?? "mic.slash")
                    .font(.system(size: 17, weight: .medium))
                    .foregroundStyle(model.selectedDevice == nil ? Color.orange : Module.system.tint)
                    .frame(width: 26)
                VStack(alignment: .leading, spacing: 1) {
                    Text(model.selectedDevice?.name ?? "No microphone")
                        .font(.system(size: 13, weight: .semibold))
                        .lineLimit(1)
                    Text(model.preferredDeviceUID == nil ? "Automatic · Bluetooth first" : "Pinned")
                        .font(.system(size: 10.5))
                        .foregroundStyle(.secondary)
                }
                Spacer(minLength: 4)
                Menu {
                    Button {
                        model.chooseDevice(uid: nil)
                    } label: {
                        Label("Automatic (any mic)", systemImage: model.preferredDeviceUID == nil ? "checkmark" : "sparkles")
                    }
                    Divider()
                    ForEach(model.inputDevices) { device in
                        Button {
                            model.chooseDevice(uid: device.uid)
                        } label: {
                            Label(device.name + (device.isBuiltIn ? " (built-in)" : ""),
                                  systemImage: model.preferredDeviceUID == device.uid ? "checkmark" : device.symbol)
                        }
                    }
                } label: {
                    Text("Change").font(.system(size: 11.5, weight: .semibold))
                }
                .menuStyle(.button)
                .buttonStyle(.bordered)
                .controlSize(.small)
                .fixedSize()
            }

            LevelMeter(level: model.phase == .listening ? model.micLevel : 0, tint: Module.system.tint)

            if model.selectedDevice?.isBuiltIn == true {
                Label("Built-in mic may be silent on this Mac — connect AirPods for voice.", systemImage: "exclamationmark.triangle.fill")
                    .font(.system(size: 10.5))
                    .foregroundStyle(.orange)
            }
        }
    }
}

struct LevelMeter: View {
    let level: Double
    let tint: Color
    private let bars = 24

    var body: some View {
        HStack(spacing: 2) {
            ForEach(0..<bars, id: \.self) { i in
                let lit = Double(i) / Double(bars) < level
                Capsule()
                    .fill(lit ? (i > bars * 3 / 4 ? Color.orange : tint) : Color.primary.opacity(0.1))
                    .frame(height: 5)
            }
        }
        .animation(.linear(duration: 0.08), value: level)
        .accessibilityLabel("Microphone level")
    }
}

struct ShortcutRow: View {
    let keys: String
    let label: String

    var body: some View {
        HStack {
            Text(label).font(.system(size: 12.5))
            Spacer()
            Text(keys)
                .font(.system(size: 11, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
                .padding(.horizontal, 7)
                .padding(.vertical, 2)
                .background(Color.primary.opacity(0.08), in: RoundedRectangle(cornerRadius: 6, style: .continuous))
        }
    }
}
