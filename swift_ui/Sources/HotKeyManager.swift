import Carbon
import AppKit

class HotKeyManager {
    static let shared = HotKeyManager()

    private var hotKeyRefs: [EventHotKeyRef] = []

    func registerHotKeys() {
        var eventType = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))

        InstallEventHandler(GetApplicationEventTarget(), { (nextHandler, theEvent, userData) -> OSStatus in
            var hotKeyID = EventHotKeyID()
            let status = GetEventParameter(
                theEvent,
                EventParamName(kEventParamDirectObject),
                EventParamType(typeEventHotKeyID),
                nil,
                MemoryLayout<EventHotKeyID>.size,
                nil,
                &hotKeyID
            )

            if status == noErr {
                DispatchQueue.main.async {
                    NotificationCenter.default.post(name: NSNotification.Name("SpeedXToggleHotKey"), object: nil)
                }
            }
            return noErr
        }, 1, &eventType, nil, nil)

        // 1. Option + Space (keyCode: 49 for Space)
        let id1 = EventHotKeyID(signature: OSType(0x53504458), id: 1) // 'SPDX'
        var ref1: EventHotKeyRef?
        let s1 = RegisterEventHotKey(49, UInt32(optionKey), id1, GetApplicationEventTarget(), 0, &ref1)
        if s1 == noErr, let r1 = ref1 {
            hotKeyRefs.append(r1)
        }

        // 2. Cmd + Shift + Space (Secondary shortcut)
        let id2 = EventHotKeyID(signature: OSType(0x53504458), id: 2)
        var ref2: EventHotKeyRef?
        let s2 = RegisterEventHotKey(49, UInt32(cmdKey | shiftKey), id2, GetApplicationEventTarget(), 0, &ref2)
        if s2 == noErr, let r2 = ref2 {
            hotKeyRefs.append(r2)
        }
    }

    deinit {
        for ref in hotKeyRefs {
            UnregisterEventHotKey(ref)
        }
    }
}
