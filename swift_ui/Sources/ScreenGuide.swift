import AppKit
import ApplicationServices
import SwiftUI

// MARK: - "Show me where": find a control by name with Accessibility and ring it

final class ScreenGuide {
    static let shared = ScreenGuide()
    private var ring: RingPanel?
    private var dismiss: DispatchWorkItem?

    /// Looks in the app the user was just in. `completion` gets a message only on failure.
    func show(query: String, in appName: String?, completion: @escaping (String?) -> Void) {
        guard AXIsProcessTrusted() else {
            let opts = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary
            _ = AXIsProcessTrustedWithOptions(opts)
            completion("Turn on Accessibility for Speed-X so I can find things on screen.")
            return
        }
        let target = NSWorkspace.shared.runningApplications.first {
            $0.localizedName == appName && $0.processIdentifier != ProcessInfo.processInfo.processIdentifier
        } ?? NSWorkspace.shared.frontmostApplication
        guard let app = target, app.processIdentifier != ProcessInfo.processInfo.processIdentifier else {
            completion("I couldn't tell which app to look in.")
            return
        }
        let pid = app.processIdentifier
        DispatchQueue.global(qos: .userInitiated).async {
            let hit = AXFinder.find(query: query, pid: pid)
            DispatchQueue.main.async {
                if let hit {
                    self.present(frame: hit.frame, label: hit.title)
                    completion(nil)
                } else {
                    completion("I couldn't find “\(query)” in \(app.localizedName ?? "that app").")
                }
            }
        }
    }

    private func present(frame: CGRect, label: String) {
        dismiss?.cancel()
        ring?.orderOut(nil)
        // AX uses a top-left origin on the primary display; AppKit is bottom-left.
        let primaryH = NSScreen.screens.first?.frame.height ?? 0
        let rect = CGRect(x: frame.minX, y: primaryH - frame.maxY, width: frame.width, height: frame.height)
        let panel = RingPanel(target: rect, label: label)
        ring = panel
        panel.orderFrontRegardless()
        let work = DispatchWorkItem { [weak self] in self?.ring?.orderOut(nil); self?.ring = nil }
        dismiss = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 5, execute: work)
    }
}

struct AXHit { let frame: CGRect; let title: String }

enum AXFinder {
    private static let skipRoles: Set<String> = ["AXScrollBar", "AXImage", "AXGroup", "AXSplitGroup", "AXLayoutArea"]

    static func find(query: String, pid: pid_t, budget: Int = 6000) -> AXHit? {
        let words = query.lowercased().split(whereSeparator: { !$0.isLetter && !$0.isNumber }).map(String.init)
            .filter { !["the", "a", "an", "button", "icon", "menu", "tab", "toggle", "option", "setting"].contains($0) || query.split(separator: " ").count == 1 }
        guard !words.isEmpty else { return nil }
        let wanted = query.lowercased()
        let root = AXUIElementCreateApplication(pid)
        AXUIElementSetMessagingTimeout(root, 1.0)
        var queue: [(AXUIElement, Int)] = [(root, 0)]
        var best: (score: Double, hit: AXHit)?
        var seen = 0
        var i = 0
        while i < queue.count, seen < budget {
            let (el, depth) = queue[i]; i += 1; seen += 1
            let role = string(el, kAXRoleAttribute) ?? ""
            if !skipRoles.contains(role), let name = label(of: el), let frame = frame(of: el), frame.width > 2, frame.height > 2 {
                let n = name.lowercased()
                var score = 0.0
                if n == wanted { score = 3 }
                else if n.contains(wanted) || wanted.contains(n) && n.count > 2 { score = 2 }
                else {
                    let hits = words.filter { n.contains($0) }.count
                    score = Double(hits) / Double(words.count)
                }
                // Prefer things you can actually click.
                if ["AXButton", "AXMenuItem", "AXMenuBarItem", "AXCheckBox", "AXRadioButton", "AXPopUpButton", "AXLink", "AXTextField", "AXTab"].contains(role) { score += 0.4 }
                if score >= 1, score > (best?.score ?? 0) { best = (score, AXHit(frame: frame, title: name)) }
            }
            if depth < 14 {
                for child in children(el) { queue.append((child, depth + 1)) }
            }
        }
        return best?.hit
    }

    private static func string(_ el: AXUIElement, _ attr: String) -> String? {
        var v: CFTypeRef?
        guard AXUIElementCopyAttributeValue(el, attr as CFString, &v) == .success, let s = v as? String, !s.isEmpty else { return nil }
        return s
    }

    private static func label(of el: AXUIElement) -> String? {
        string(el, kAXTitleAttribute) ?? string(el, kAXDescriptionAttribute) ?? string(el, kAXLabelValueAttribute as String) ?? string(el, kAXHelpAttribute)
    }

    private static func children(_ el: AXUIElement) -> [AXUIElement] {
        var v: CFTypeRef?
        guard AXUIElementCopyAttributeValue(el, kAXChildrenAttribute as CFString, &v) == .success, let arr = v as? [AXUIElement] else { return [] }
        return arr
    }

    private static func frame(of el: AXUIElement) -> CGRect? {
        var p: CFTypeRef?, s: CFTypeRef?
        guard AXUIElementCopyAttributeValue(el, kAXPositionAttribute as CFString, &p) == .success,
              AXUIElementCopyAttributeValue(el, kAXSizeAttribute as CFString, &s) == .success,
              let pv = p, let sv = s else { return nil }
        var point = CGPoint.zero, size = CGSize.zero
        guard AXValueGetValue(pv as! AXValue, .cgPoint, &point), AXValueGetValue(sv as! AXValue, .cgSize, &size) else { return nil }
        return CGRect(origin: point, size: size)
    }
}

final class RingPanel: NSPanel {
    init(target: CGRect, label: String) {
        let pad: CGFloat = 40
        let frame = target.insetBy(dx: -pad, dy: -pad)
        super.init(contentRect: frame, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        isOpaque = false
        backgroundColor = .clear
        hasShadow = false
        level = .screenSaver
        ignoresMouseEvents = true
        collectionBehavior = [.canJoinAllSpaces, .stationary, .ignoresCycle, .fullScreenAuxiliary]
        let view = RingView(size: target.size, label: label).frame(width: frame.width, height: frame.height)
        contentView = NSHostingView(rootView: view)
        setFrame(frame, display: false)
    }
    override var canBecomeKey: Bool { false }
}

struct RingView: View {
    let size: CGSize
    let label: String
    @State private var pulse = false

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: min(size.height, 40) / 2 + 6, style: .continuous)
                .stroke(Color.orange, lineWidth: 4)
                .frame(width: size.width + 14, height: size.height + 14)
                .scaleEffect(pulse ? 1.12 : 1)
                .opacity(pulse ? 0.35 : 1)
                .shadow(color: .orange.opacity(0.7), radius: 10)
            RoundedRectangle(cornerRadius: min(size.height, 40) / 2 + 6, style: .continuous)
                .stroke(Color.orange, lineWidth: 3)
                .frame(width: size.width + 14, height: size.height + 14)
        }
        .onAppear { withAnimation(.easeInOut(duration: 0.8).repeatForever(autoreverses: true)) { pulse = true } }
        .accessibilityLabel("Here: \(label)")
    }
}

// MARK: - Pen: draw on the screen (strokes stay until you stop or clear)

final class PenOverlay {
    static let shared = PenOverlay()
    private var windows: [PenWindow] = []
    var isOn: Bool { !windows.isEmpty }

    func start() {
        guard !isOn else { return }
        windows = NSScreen.screens.map { screen in
            let w = PenWindow(screen: screen)
            w.onEscape = { [weak self] in self?.stop() }
            w.makeKeyAndOrderFront(nil)
            return w
        }
        NSApp.activate(ignoringOtherApps: true)
    }

    func stop() {
        windows.forEach { $0.orderOut(nil) }
        windows = []
    }

    func clear() { windows.forEach { $0.canvas.clear() } }
}

final class PenWindow: NSPanel {
    let canvas: PenCanvas
    var onEscape: (() -> Void)?

    init(screen: NSScreen) {
        canvas = PenCanvas(frame: NSRect(origin: .zero, size: screen.frame.size))
        super.init(contentRect: screen.frame, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        isOpaque = false
        backgroundColor = NSColor.black.withAlphaComponent(0.001)   // receives clicks but is see-through
        hasShadow = false
        level = .screenSaver
        collectionBehavior = [.canJoinAllSpaces, .stationary, .ignoresCycle, .fullScreenAuxiliary]
        contentView = canvas
    }

    override var canBecomeKey: Bool { true }
    override func keyDown(with event: NSEvent) {
        if event.keyCode == 53 { onEscape?() } else { super.keyDown(with: event) }
    }
}

final class PenCanvas: NSView {
    private var strokes: [NSBezierPath] = []
    private var current: NSBezierPath?

    func clear() { strokes = []; current = nil; needsDisplay = true }

    override func mouseDown(with event: NSEvent) {
        let p = NSBezierPath()
        p.lineWidth = 4; p.lineCapStyle = .round; p.lineJoinStyle = .round
        p.move(to: convert(event.locationInWindow, from: nil))
        current = p
    }

    override func mouseDragged(with event: NSEvent) {
        current?.line(to: convert(event.locationInWindow, from: nil))
        needsDisplay = true
    }

    override func mouseUp(with event: NSEvent) {
        if let c = current { strokes.append(c) }
        current = nil
    }

    override func draw(_ dirtyRect: NSRect) {
        NSColor.systemRed.setStroke()
        for s in strokes + (current.map { [$0] } ?? []) { s.stroke() }
    }

    override var acceptsFirstResponder: Bool { true }
}
