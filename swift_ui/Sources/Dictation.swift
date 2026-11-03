import AppKit
import ApplicationServices
import Observation
import SwiftUI

/// Live state for the dictation pill.
@Observable
final class DictationState {
    static let shared = DictationState()
    var active = false
    var locked = false
    var level: Double = 0
    var text = ""
    var notice: String?
}

/// Dictate into any text field: hold fn (or press ⌥⇧Space), talk, let go. The raw on-device transcript is
/// cleaned by the engine (fillers, "scratch that", spoken punctuation, personal dictionary) and pasted at
/// the cursor of whatever app is in front.
///
/// fn: hold to talk; a quick tap locks it on (hands-free) and the next tap inserts.
/// Needs Input Monitoring for the fn key and Accessibility to paste; ⌥⇧Space works without the former.
final class DictationController {
    static let shared = DictationController()

    static let enabledKey = "SpeedXDictation"
    var enabled: Bool {
        get { UserDefaults.standard.object(forKey: Self.enabledKey) as? Bool ?? true }
        set { UserDefaults.standard.set(newValue, forKey: Self.enabledKey) }
    }

    private let state = DictationState.shared
    private var monitors: [Any] = []
    private var fnDownAt: Date?
    private var hud: DictationHUD?
    private var busy = false

    // MARK: - Triggers

    func install() {
        let handler: (NSEvent) -> Void = { [weak self] event in self?.flagsChanged(event) }
        if let global = NSEvent.addGlobalMonitorForEvents(matching: .flagsChanged, handler: handler) { monitors.append(global) }
        if let local = NSEvent.addLocalMonitorForEvents(matching: .flagsChanged, handler: { event in handler(event); return event }) {
            monitors.append(local)
        }
    }

    private func flagsChanged(_ event: NSEvent) {
        guard enabled else { return }
        let fn = event.modifierFlags.contains(.function)
        // fn + another modifier (fn+control…) is some other shortcut.
        let others = event.modifierFlags.intersection([.command, .option, .control, .shift])
        if fn, fnDownAt == nil, others.isEmpty {
            fnDownAt = Date()
            if state.active, state.locked { stopAndInsert(); fnDownAt = nil; return }
            start(locked: false)
        } else if !fn, let down = fnDownAt {
            fnDownAt = nil
            guard state.active else { return }
            if Date().timeIntervalSince(down) < 0.3 {
                state.locked = true   // a tap: keep listening until the next fn press
            } else {
                stopAndInsert()
            }
        }
    }

    /// ⌥⇧Space.
    func toggle() {
        if state.active { stopAndInsert() } else { start(locked: true) }
    }

    // MARK: - Session

    private func start(locked: Bool) {
        let speech = SpeechManager.shared
        guard !speech.isRecording, !busy else { return }
        state.text = ""
        state.notice = nil
        state.locked = locked
        state.level = 0
        speech.dictationMode = true
        speech.dictationHandler = { [weak self] raw in self?.finish(raw) }
        speech.onDictationPartial = { [weak self] text in self?.state.text = text }
        state.active = true
        showHUD()
        NSSound(named: "Tink")?.play()
        speech.start()
        // start() reports failures through onError and never begins recording
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) { [weak self] in
            if self?.state.active == true, !speech.isRecording { self?.end() }
        }
    }

    private func stopAndInsert() {
        guard state.active else { return }
        if SpeechManager.shared.isRecording {
            SpeechManager.shared.stop(.manual)   // delivers to dictationHandler, or nothing if silent
        }
        // No words came back: close the pill shortly.
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { [weak self] in
            if self?.state.active == true, self?.busy == false { self?.end() }
        }
    }

    func cancel() {
        guard state.active else { return }
        SpeechManager.shared.cancel()
        end()
    }

    private func finish(_ raw: String) {
        busy = true
        EngineClient.shared.dictate(raw) { [weak self] resp in
            guard let self else { return }
            let text = resp.text ?? raw
            self.insert(text)
            self.busy = false
            self.end()
        }
    }

    private func end() {
        let speech = SpeechManager.shared
        speech.dictationMode = false
        speech.dictationHandler = nil
        speech.onDictationPartial = nil
        state.active = false
        state.locked = false
        state.level = 0
        let notice = state.notice
        DispatchQueue.main.asyncAfter(deadline: .now() + (notice == nil ? 0.05 : 2.2)) { [weak self] in
            if self?.state.active == false { self?.hud?.orderOut(nil) }
        }
    }

    // MARK: - Insert

    /// Paste at the cursor, then put the user's clipboard back.
    private func insert(_ text: String) {
        guard !text.isEmpty else { return }
        let pb = NSPasteboard.general
        let saved: [[NSPasteboard.PasteboardType: Data]] = (pb.pasteboardItems ?? []).map { item in
            var copy: [NSPasteboard.PasteboardType: Data] = [:]
            for type in item.types { if let d = item.data(forType: type) { copy[type] = d } }
            return copy
        }
        pb.clearContents()
        pb.setString(text, forType: .string)
        guard AXIsProcessTrusted() else {
            state.notice = "Copied — turn on Accessibility for Speed-X to paste automatically."
            return
        }
        let source = CGEventSource(stateID: .combinedSessionState)
        let down = CGEvent(keyboardEventSource: source, virtualKey: 9, keyDown: true)   // V
        let up = CGEvent(keyboardEventSource: source, virtualKey: 9, keyDown: false)
        down?.flags = .maskCommand
        up?.flags = .maskCommand
        down?.post(tap: .cgAnnotatedSessionEventTap)
        up?.post(tap: .cgAnnotatedSessionEventTap)
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) {
            pb.clearContents()
            for item in saved {
                let new = NSPasteboardItem()
                for (type, data) in item { new.setData(data, forType: type) }
                pb.writeObjects([new])
            }
        }
    }

    // MARK: - HUD

    private func showHUD() {
        if hud == nil { hud = DictationHUD() }
        hud?.present()
    }
}

// MARK: - Pill

final class DictationHUD: NSPanel {
    init() {
        super.init(
            contentRect: NSRect(x: 0, y: 0, width: 420, height: 64),
            styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false
        )
        isOpaque = false
        backgroundColor = .clear
        hasShadow = false
        level = .statusBar
        collectionBehavior = [.canJoinAllSpaces, .stationary, .ignoresCycle, .fullScreenAuxiliary]
        ignoresMouseEvents = true
        let host = NSHostingView(rootView: DictationPill())
        host.frame = NSRect(x: 0, y: 0, width: 420, height: 64)
        contentView = host
    }

    override var canBecomeKey: Bool { false }

    func present() {
        guard let screen = NSScreen.main else { return }
        let f = screen.visibleFrame
        setFrameOrigin(NSPoint(x: f.midX - frame.width / 2, y: f.minY + 48))
        orderFrontRegardless()
    }
}

struct DictationPill: View {
    private var state = DictationState.shared

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: state.notice == nil ? "mic.fill" : "doc.on.clipboard")
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(state.notice == nil ? Color.red : Color.orange)
            if let notice = state.notice {
                Text(notice).font(.system(size: 12, weight: .medium)).lineLimit(2)
            } else {
                Bars(level: state.level).frame(width: 34, height: 18)
                Text(state.text.isEmpty ? (state.locked ? "Listening — tap fn to insert" : "Listening…") : state.text)
                    .font(.system(size: 12.5, weight: .medium))
                    .lineLimit(1)
                    .truncationMode(.head)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .padding(.horizontal, 16)
        .frame(width: 420, height: 44)
        .glassEffect(.regular, in: Capsule())
        .overlay(Capsule().strokeBorder(Color.orange.opacity(state.locked ? 0.9 : 0), lineWidth: 2))   // locked: orange ring
        .frame(width: 420, height: 64)
    }

    private struct Bars: View {
        let level: Double
        var body: some View {
            HStack(spacing: 3) {
                ForEach(0..<5, id: \.self) { i in
                    let h = 4 + 14 * max(0.1, min(1, level * (0.6 + 0.1 * Double((i * 3) % 5))))
                    Capsule().fill(Color.primary.opacity(0.8)).frame(width: 3, height: h)
                }
            }
            .animation(.easeOut(duration: 0.08), value: level)
        }
    }
}
