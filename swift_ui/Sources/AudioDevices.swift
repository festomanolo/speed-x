import CoreAudio
import Foundation

/// An audio input device as seen by CoreAudio.
struct AudioInputDevice: Identifiable, Hashable {
    let id: AudioDeviceID
    let uid: String
    let name: String
    let transport: UInt32
    let channels: Int
    let isDefault: Bool

    var isBluetooth: Bool {
        transport == kAudioDeviceTransportTypeBluetooth || transport == kAudioDeviceTransportTypeBluetoothLE
    }
    var isBuiltIn: Bool { transport == kAudioDeviceTransportTypeBuiltIn }
    var isUSB: Bool { transport == kAudioDeviceTransportTypeUSB }
    var isVirtual: Bool { transport == kAudioDeviceTransportTypeVirtual || transport == kAudioDeviceTransportTypeAggregate }

    var symbol: String {
        let lower = name.lowercased()
        if lower.contains("airpods max") { return "airpodsmax" }
        if lower.contains("airpods pro") { return "airpodspro" }
        if lower.contains("airpods") { return "airpods" }
        if isBluetooth { return "headphones" }
        if isUSB { return "cable.connector" }
        if isVirtual { return "waveform.circle" }
        return "mic"
    }
}

/// Enumerates input devices and picks the one Speed-X should listen on.
///
/// Automatic choice works with any microphone: the input selected in macOS wins when it is
/// a real external device, otherwise wired mics (USB, then other external hardware) come
/// before Bluetooth headsets. On this Hackintosh the "Built-in Microphone" is reported as
/// the default input but delivers silence, so built-in hardware is only a last resort and
/// virtual loopback devices are never picked over a real mic. The user can pin a specific
/// device; that choice is remembered by UID.
final class AudioDevices {
    static let shared = AudioDevices()
    static let preferredKey = "SpeedXPreferredInputUID"

    var onChange: (() -> Void)?

    private init() {
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDevices,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        AudioObjectAddPropertyListenerBlock(AudioObjectID(kAudioObjectSystemObject), &address, DispatchQueue.main) { [weak self] _, _ in
            self?.onChange?()
        }
        var defAddress = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDefaultInputDevice,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        AudioObjectAddPropertyListenerBlock(AudioObjectID(kAudioObjectSystemObject), &defAddress, DispatchQueue.main) { [weak self] _, _ in
            self?.onChange?()
        }
    }

    /// nil = automatic selection.
    var preferredUID: String? {
        get { UserDefaults.standard.string(forKey: Self.preferredKey) }
        set { UserDefaults.standard.set(newValue, forKey: Self.preferredKey) }
    }

    func inputDevices() -> [AudioInputDevice] {
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDevices,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        var size: UInt32 = 0
        guard AudioObjectGetPropertyDataSize(AudioObjectID(kAudioObjectSystemObject), &address, 0, nil, &size) == noErr else { return [] }
        var ids = [AudioDeviceID](repeating: 0, count: Int(size) / MemoryLayout<AudioDeviceID>.size)
        guard AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &address, 0, nil, &size, &ids) == noErr else { return [] }

        let defaultID = defaultInputID()
        return ids.compactMap { id in
            let channels = inputChannelCount(id)
            guard channels > 0 else { return nil }
            return AudioInputDevice(
                id: id,
                uid: stringProperty(id, kAudioDevicePropertyDeviceUID) ?? "\(id)",
                name: stringProperty(id, kAudioObjectPropertyName) ?? "Input \(id)",
                transport: uint32Property(id, kAudioDevicePropertyTransportType) ?? 0,
                channels: channels,
                isDefault: id == defaultID
            )
        }
    }

    /// The device Speed-X will record from right now.
    func selectedDevice() -> AudioInputDevice? {
        let devices = inputDevices()
        if let uid = preferredUID, let pinned = devices.first(where: { $0.uid == uid }) {
            return pinned
        }
        return Self.automaticChoice(devices)
    }

    static func automaticChoice(_ devices: [AudioInputDevice]) -> AudioInputDevice? {
        func rank(_ d: AudioInputDevice) -> Int {
            let external = !d.isBuiltIn && !d.isVirtual
            if d.isDefault && external { return 0 }                  // whatever macOS is set to
            if d.isUSB { return 1 }
            if external && !d.isBluetooth { return 2 }                // other wired / Thunderbolt
            if d.isBluetooth { return 3 }                             // AirPods & headsets
            if d.isBuiltIn { return 4 }
            return 5 // virtual loopback devices (BoomAudio etc.) never carry a voice
        }
        return devices.min { a, b in
            let ra = rank(a), rb = rank(b)
            if ra != rb { return ra < rb }
            return a.isDefault && !b.isDefault
        }
    }

    // MARK: - CoreAudio helpers

    private func defaultInputID() -> AudioDeviceID {
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDefaultInputDevice,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        var id = AudioDeviceID(0)
        var size = UInt32(MemoryLayout<AudioDeviceID>.size)
        AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &address, 0, nil, &size, &id)
        return id
    }

    private func inputChannelCount(_ id: AudioDeviceID) -> Int {
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioDevicePropertyStreamConfiguration,
            mScope: kAudioDevicePropertyScopeInput,
            mElement: kAudioObjectPropertyElementMain
        )
        var size: UInt32 = 0
        guard AudioObjectGetPropertyDataSize(id, &address, 0, nil, &size) == noErr, size > 0 else { return 0 }
        let raw = UnsafeMutableRawPointer.allocate(byteCount: Int(size), alignment: MemoryLayout<AudioBufferList>.alignment)
        defer { raw.deallocate() }
        guard AudioObjectGetPropertyData(id, &address, 0, nil, &size, raw) == noErr else { return 0 }
        let list = UnsafeMutableAudioBufferListPointer(raw.assumingMemoryBound(to: AudioBufferList.self))
        return list.reduce(0) { $0 + Int($1.mNumberChannels) }
    }

    private func stringProperty(_ id: AudioDeviceID, _ selector: AudioObjectPropertySelector) -> String? {
        var address = AudioObjectPropertyAddress(mSelector: selector, mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
        var value: Unmanaged<CFString>?
        var size = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)
        guard AudioObjectGetPropertyData(id, &address, 0, nil, &size, &value) == noErr, let cf = value?.takeRetainedValue() else { return nil }
        return cf as String
    }

    private func uint32Property(_ id: AudioDeviceID, _ selector: AudioObjectPropertySelector) -> UInt32? {
        var address = AudioObjectPropertyAddress(mSelector: selector, mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
        var value: UInt32 = 0
        var size = UInt32(MemoryLayout<UInt32>.size)
        guard AudioObjectGetPropertyData(id, &address, 0, nil, &size, &value) == noErr else { return nil }
        return value
    }
}
