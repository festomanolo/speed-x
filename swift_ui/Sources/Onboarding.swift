import AppKit
import AVFoundation
import Observation
import Speech
import SwiftUI

/// What Speed-X needs from macOS and what each permission is for. One window, live status, one button per row.
enum PermissionKind: String, CaseIterable, Identifiable {
    case microphone, speech, accessibility, inputMonitoring, screen, automation
    var id: String { rawValue }

    var title: String {
        switch self {
        case .microphone: return "Microphone"
        case .speech: return "Speech Recognition"
        case .accessibility: return "Accessibility"
        case .inputMonitoring: return "Input Monitoring"
        case .screen: return "Screen Recording"
        case .automation: return "Automation"
        }
    }

    var reason: String {
        switch self {
        case .microphone: return "Hear your commands, dictation and meetings. Audio stays on this Mac."
        case .speech: return "Turn your voice into text on-device."
        case .accessibility: return "Paste dictation, message apps, and ring things for “show me where”."
        case .inputMonitoring: return "Notice the fn key for hold-to-dictate. Optional: ⌥⇧Space works without it."
        case .screen: return "“Read my screen”. Optional."
        case .automation: return "Control Music, Notes, Mail… macOS asks the first time each is used."
        }
    }

    var required: Bool { self == .microphone || self == .speech }

    var settingsURL: String {
        switch self {
        case .microphone: return "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone"
        case .speech: return "x-apple.systempreferences:com.apple.preference.security?Privacy_SpeechRecognition"
        case .accessibility: return "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
        case .inputMonitoring: return "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"
        case .screen: return "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
        case .automation: return "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation"
        }
    }

    /// nil = macOS doesn't let apps ask (Automation): shown as "asked when used".
    var granted: Bool? {
        switch self {
        case .microphone: return AVCaptureDevice.authorizationStatus(for: .audio) == .authorized
        case .speech: return SFSpeechRecognizer.authorizationStatus() == .authorized
        case .accessibility: return AXIsProcessTrusted()
        case .inputMonitoring: return CGPreflightListenEventAccess()
        case .screen: return CGPreflightScreenCaptureAccess()
        case .automation: return nil
        }
    }

    /// Ask the system when it can still ask; otherwise (or when it only shows a pointer) open the right Settings pane.
    func grant() {
        let open = { if let url = URL(string: self.settingsURL) { NSWorkspace.shared.open(url) } }
        switch self {
        case .microphone:
            if AVCaptureDevice.authorizationStatus(for: .audio) == .notDetermined { AVCaptureDevice.requestAccess(for: .audio) { _ in } } else { open() }
        case .speech:
            if SFSpeechRecognizer.authorizationStatus() == .notDetermined { SFSpeechRecognizer.requestAuthorization { _ in } } else { open() }
        case .accessibility:
            _ = AXIsProcessTrustedWithOptions([kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary)
        case .inputMonitoring:
            _ = CGRequestListenEventAccess()
        case .screen:
            _ = CGRequestScreenCaptureAccess()
        case .automation:
            open()
        }
    }
}

@Observable
final class PermissionsModel {
    var tick = 0
    @ObservationIgnored private var timer: Timer?

    func start() {
        timer?.invalidate()
        timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in self?.tick += 1 }
    }
    func stop() { timer?.invalidate(); timer = nil }
}

struct PermissionsView: View {
    var model = PermissionsModel()
    var done: () -> Void

    var body: some View {
        _ = model.tick   // re-read statuses every second
        return VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 12) {
                Image(systemName: "waveform.circle.fill").font(.system(size: 34)).foregroundStyle(Module.assistant.tint)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Set up Speed-X").font(.system(size: 20, weight: .semibold))
                    Text("Everything runs on this Mac. Grant what you want to use; you can come back any time.")
                        .font(.system(size: 12)).foregroundStyle(.secondary)
                }
            }
            VStack(spacing: 8) {
                ForEach(PermissionKind.allCases) { kind in row(kind) }
            }
            HStack {
                Text("Say “check permissions” or open Speed-X → System any time.").font(.system(size: 11)).foregroundStyle(.secondary)
                Spacer()
                Button("Done", action: done).keyboardShortcut(.defaultAction)
            }
        }
        .padding(22)
        .frame(width: 520)
        .onAppear { model.start() }
        .onDisappear { model.stop() }
    }

    private func row(_ kind: PermissionKind) -> some View {
        let state = kind.granted
        return HStack(spacing: 12) {
            Image(systemName: state == true ? "checkmark.circle.fill" : state == false ? (kind.required ? "exclamationmark.circle.fill" : "circle") : "bolt.circle")
                .font(.system(size: 20))
                .foregroundStyle(state == true ? Color.green : state == false ? (kind.required ? Color.orange : Color.secondary) : Color.secondary)
            VStack(alignment: .leading, spacing: 1) {
                HStack(spacing: 6) {
                    Text(kind.title).font(.system(size: 13, weight: .semibold))
                    if kind.required { Text("needed").font(.system(size: 9, weight: .bold)).padding(.horizontal, 5).padding(.vertical, 1).background(Color.orange.opacity(0.2), in: Capsule()) }
                }
                Text(kind.reason).font(.system(size: 11)).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 8)
            if state == true {
                Text("On").font(.system(size: 11, weight: .medium)).foregroundStyle(.green)
            } else {
                Button(state == nil ? "Open Settings" : "Grant") { kind.grant() }.controlSize(.small)
            }
        }
        .padding(10)
        .background(Color.primary.opacity(0.05), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
    }
}

final class OnboardingWindow {
    static let shared = OnboardingWindow()
    static let doneKey = "SpeedXOnboarded"
    private var window: NSWindow?

    static var needed: Bool { !UserDefaults.standard.bool(forKey: doneKey) }

    func show() {
        if let window { window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true); return }
        let hosting = NSHostingController(rootView: PermissionsView(done: { [weak self] in self?.close() }))
        let w = NSWindow(contentViewController: hosting)
        w.title = "Speed-X Setup"
        w.styleMask = [.titled, .closable]
        w.isReleasedWhenClosed = false
        w.center()
        window = w
        w.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    private func close() {
        UserDefaults.standard.set(true, forKey: Self.doneKey)
        window?.close()
        window = nil
        SpeechManager.shared.prewarm()
    }
}
