import AppKit
import Carbon

/// Global shortcuts: ⌥Space talks to Speed-X, ⌘⇧Space opens it for typing, ⌘⌥P shows / hides the notch.
final class HotKeyManager {
    static let shared = HotKeyManager()
    static let notification = Notification.Name("SpeedXHotKey")
    static let voiceID: UInt32 = 1
    static let typeID: UInt32 = 2
    static let toggleID: UInt32 = 3

    private var hotKeyRefs: [EventHotKeyRef] = []

    func registerHotKeys() {
        var eventType = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))

        InstallEventHandler(GetApplicationEventTarget(), { _, event, _ -> OSStatus in
            var hotKeyID = EventHotKeyID()
            let status = GetEventParameter(
                event, EventParamName(kEventParamDirectObject), EventParamType(typeEventHotKeyID),
                nil, MemoryLayout<EventHotKeyID>.size, nil, &hotKeyID
            )
            if status == noErr {
                let id = hotKeyID.id
                DispatchQueue.main.async {
                    NotificationCenter.default.post(name: HotKeyManager.notification, object: nil, userInfo: ["id": id])
                }
            }
            return noErr
        }, 1, &eventType, nil, nil)

        register(keyCode: 49, modifiers: UInt32(optionKey), id: Self.voiceID)            // ⌥ Space
        register(keyCode: 49, modifiers: UInt32(cmdKey | shiftKey), id: Self.typeID)     // ⌘ ⇧ Space
        register(keyCode: 35, modifiers: UInt32(cmdKey | optionKey), id: Self.toggleID)  // ⌘ ⌥ P
    }

    private func register(keyCode: UInt32, modifiers: UInt32, id: UInt32) {
        let hotKeyID = EventHotKeyID(signature: OSType(0x53504458), id: id) // 'SPDX'
        var ref: EventHotKeyRef?
        if RegisterEventHotKey(keyCode, modifiers, hotKeyID, GetApplicationEventTarget(), 0, &ref) == noErr, let ref {
            hotKeyRefs.append(ref)
        }
    }

    deinit {
        hotKeyRefs.forEach { UnregisterEventHotKey($0) }
    }
}
