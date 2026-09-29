import AppKit
import SwiftUI

final class SpeedXPanel: NSPanel {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { false }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var window: SpeedXPanel!
    private let model = AppModel()
    private var regions: [String: CGRect] = [:]
    private var pointerTimer: Timer?
    private var statsTimer: Timer?

    private var hoverModule: Module?
    private var hoverSince = Date()
    private var outsideSince: Date?

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)

        EngineClient.shared.start()
        buildWindow()

        HotKeyManager.shared.registerHotKeys()
        NotificationCenter.default.addObserver(self, selector: #selector(hotKey(_:)), name: HotKeyManager.notification, object: nil)
        NotificationCenter.default.addObserver(self, selector: #selector(placeWindow), name: NSApplication.didChangeScreenParametersNotification, object: nil)
        NSWorkspace.shared.notificationCenter.addObserver(self, selector: #selector(appActivated(_:)), name: NSWorkspace.didActivateApplicationNotification, object: nil)
        model.lastExternalApp = NSWorkspace.shared.frontmostApplication?.localizedName

        SpeechManager.shared.requestPermissions { granted in
            if granted { SpeechManager.shared.prewarm() }
        }

        if !UserDefaults.standard.bool(forKey: "SpeedXLoginConfigured") {
            UserDefaults.standard.set(true, forKey: "SpeedXLoginConfigured")
            model.launchAtLogin = LaunchAtLoginManager.shared.setEnabled(true)
        }

        statsTimer = Timer.scheduledTimer(withTimeInterval: 2.0, repeats: true) { [weak self] _ in self?.model.refreshStats() }
        pointerTimer = Timer.scheduledTimer(withTimeInterval: 1.0 / 30.0, repeats: true) { [weak self] _ in self?.trackPointer() }
        RunLoop.main.add(pointerTimer!, forMode: .common)
    }

    func applicationWillTerminate(_ notification: Notification) {
        EngineClient.shared.shutdown()
    }

    // MARK: - Window

    private func buildWindow() {
        window = SpeedXPanel(
            contentRect: NSRect(origin: .zero, size: Layout.windowSize),
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        window.isOpaque = false
        window.backgroundColor = .clear
        window.hasShadow = false
        window.level = .floating
        window.collectionBehavior = [.canJoinAllSpaces, .stationary, .ignoresCycle, .fullScreenAuxiliary]
        window.isMovable = false
        window.hidesOnDeactivate = false
        window.ignoresMouseEvents = true

        let root = RootView(model: model) { [weak self] regions in self?.regions = regions }
        let host = NSHostingView(rootView: root)
        host.frame = NSRect(origin: .zero, size: Layout.windowSize)
        host.sizingOptions = []
        window.contentView = host
        placeWindow()
        window.orderFrontRegardless()
    }

    @objc private func placeWindow() {
        guard let screen = NSScreen.main else { return }
        let visible = screen.visibleFrame
        let size = Layout.windowSize
        window.setFrame(NSRect(x: screen.frame.maxX - size.width, y: visible.maxY - size.height, width: size.width, height: size.height), display: true)
    }

    // MARK: - Pointer: click-through outside the glass, hover to peek, leave to dismiss

    private func trackPointer() {
        guard let window else { return }
        guard model.isShown else {
            // Hidden in the bezel: never intercept clicks or hover-peek.
            if !window.ignoresMouseEvents { window.ignoresMouseEvents = true }
            return
        }
        let p = window.convertPoint(fromScreen: NSEvent.mouseLocation)
        let point = CGPoint(x: p.x, y: window.frame.height - p.y)
        let inside = regions.values.contains { $0.insetBy(dx: -6, dy: -6).contains(point) }
        if window.ignoresMouseEvents == inside { window.ignoresMouseEvents = !inside }

        let hovered = Module.allCases.first { regions["module.\($0.rawValue)"]?.contains(point) == true }
        if hovered != hoverModule {
            hoverModule = hovered
            hoverSince = Date()
        }
        if let hovered, !model.isPinned, model.activeModule != hovered, Date().timeIntervalSince(hoverSince) > 0.18 {
            withAnimation(Motion.standard) { model.open(hovered, pin: false) }
        }

        if inside {
            outsideSince = nil
        } else if model.activeModule != nil, !model.isPinned, model.phase != .listening, model.phase != .thinking {
            if outsideSince == nil { outsideSince = Date() }
            if let since = outsideSince, Date().timeIntervalSince(since) > 0.4 {
                withAnimation(Motion.standard) { model.close() }
                outsideSince = nil
            }
        }
    }

    // MARK: - Hotkeys

    @objc private func hotKey(_ note: Notification) {
        let id = note.userInfo?["id"] as? UInt32 ?? 1
        if id == HotKeyManager.toggleID {
            toggleNotch()
            return
        }
        if !model.isShown { withAnimation(Motion.emerge) { model.show() } }
        if id == HotKeyManager.voiceID {
            if model.phase == .listening {
                SpeechManager.shared.stop(.manual)
                return
            }
            model.startListening()
            withAnimation(Motion.standard) { model.open(.assistant, pin: true) }
        } else {
            if model.activeModule == .assistant && model.isPinned && window.isKeyWindow {
                withAnimation(Motion.standard) { model.close() }
                window.resignKey()
                return
            }
            withAnimation(Motion.standard) { model.open(.assistant, pin: true) }
            window.ignoresMouseEvents = false
            window.makeKeyAndOrderFront(nil)
            model.focusInputToken += 1
        }
    }

    /// ⌘⌥P: slide the notch out of the bezel, or tuck it (and any open card) back in.
    private func toggleNotch() {
        if model.isShown {
            withAnimation(Motion.retract) { model.hide() }
            regions = [:]
            window.ignoresMouseEvents = true
            if window.isKeyWindow { window.resignKey() }
        } else {
            window.orderFrontRegardless()
            withAnimation(Motion.emerge) { model.show() }
        }
    }

    // MARK: - URL scheme: speedx://open/<engine|system|assistant>, speedx://listen, speedx://run?cmd=…, speedx://close,
    //         speedx://toggle, speedx://show, speedx://hide

    func application(_ application: NSApplication, open urls: [URL]) {
        for url in urls {
            let host = url.host ?? ""
            switch host {
            case "toggle":
                toggleNotch()
                continue
            case "hide":
                if model.isShown { toggleNotch() }
                continue
            case "show", "open", "listen", "run":
                if !model.isShown { toggleNotch() }
            default:
                break
            }
            switch host {
            case "open":
                let name = url.pathComponents.dropFirst().first ?? "assistant"
                if let module = Module(rawValue: name) {
                    withAnimation(Motion.standard) { model.open(module, pin: true) }
                }
            case "listen":
                model.startListening()
                withAnimation(Motion.standard) { model.open(.assistant, pin: true) }
            case "run":
                let cmd = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems?.first { $0.name == "cmd" }?.value ?? ""
                guard !cmd.isEmpty else { continue }
                model.lastCommandWasVoice = false
                model.submit(cmd)
                withAnimation(Motion.standard) { model.open(.assistant, pin: true) }
            case "close":
                withAnimation(Motion.standard) { model.close() }
            default:
                break
            }
        }
    }

    @objc private func appActivated(_ note: Notification) {
        guard let app = note.userInfo?[NSWorkspace.applicationUserInfoKey] as? NSRunningApplication,
              app.processIdentifier != ProcessInfo.processInfo.processIdentifier else { return }
        model.lastExternalApp = app.localizedName
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
