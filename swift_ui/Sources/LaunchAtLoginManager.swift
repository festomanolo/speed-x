import Foundation
import ServiceManagement

class LaunchAtLoginManager {
    static let shared = LaunchAtLoginManager()

    var isEnabled: Bool {
        if #available(macOS 13.0, *) {
            return SMAppService.mainApp.status == .enabled
        }
        return false
    }

    @discardableResult
    func setEnabled(_ enabled: Bool) -> Bool {
        if #available(macOS 13.0, *) {
            do {
                if enabled {
                    try SMAppService.mainApp.register()
                } else {
                    try SMAppService.mainApp.unregister()
                }
                return isEnabled
            } catch {
                print("LaunchAtLoginManager: SMAppService error: \(error)")
                return isEnabled
            }
        }
        return false
    }

    @discardableResult
    func toggle() -> Bool {
        let current = isEnabled
        return setEnabled(!current)
    }
}
