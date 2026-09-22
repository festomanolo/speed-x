import AppKit

class SpeedXPanel: NSPanel {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { true }
}

class AppDelegate: NSObject, NSApplicationDelegate {
    var window: SpeedXPanel!
    var islandView: IslandView!
    var timer: Timer?

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory) // Runs as a sleek agent without dock icon

        guard let screen = NSScreen.main else { return }
        let screenFrame = screen.frame
        let visibleFrame = screen.visibleFrame

        let winWidth: CGFloat = 380
        let winHeight: CGFloat = 360

        // Position: Hugging the far right edge of the screen, just beneath the top menu bar
        let originX = screenFrame.maxX - winWidth
        let originY = visibleFrame.maxY - winHeight + 10

        let winRect = NSRect(x: originX, y: originY, width: winWidth, height: winHeight)

        window = SpeedXPanel(
            contentRect: winRect,
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )

        window.isOpaque = false
        window.backgroundColor = .clear
        window.hasShadow = false
        window.level = .floating
        window.collectionBehavior = [.canJoinAllSpaces, .stationary, .ignoresCycle]
        window.isMovable = false
        window.acceptsMouseMovedEvents = true

        islandView = IslandView(frame: NSRect(x: 0, y: 0, width: winWidth, height: winHeight))
        window.contentView = islandView
        window.orderFrontRegardless()

        // 1. Register Global HotKeys (Option+Space and Cmd+Shift+Space)
        HotKeyManager.shared.registerHotKeys()

        // 2. Request microphone & speech permissions gracefully in background
        SpeechManager.shared.requestPermissions { granted in
            if granted {
                print("Speed-X: Microphone and offline Speech Recognition authorized.")
            }
        }

        // 3. Register Launch at Login if installed in Applications
        _ = LaunchAtLoginManager.shared.setEnabled(true)

        // 4. Timer for live stats update
        timer = Timer.scheduledTimer(withTimeInterval: 1.5, repeats: true) { [weak self] _ in
            self?.islandView.updateMetrics()
        }
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
