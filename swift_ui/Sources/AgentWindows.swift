import AppKit
import Observation
import SwiftUI

struct AgentItem: Identifiable, Equatable {
    let id: Int
    var command: String
    var status: String      // running | done | failed | stopped | needs_approval
    var message: String
    var lines: [String]
    var elapsed: Double
}

/// Background agents: commands that run while you keep working. Each shows as a small glass card in a
/// floating panel at the bottom-left of the screen; the panel only exists while there are agents.
@Observable
final class AgentCenter {
    static let shared = AgentCenter()
    var items: [AgentItem] = []
    @ObservationIgnored private var panel: AgentPanel?

    func update(_ e: EngineResponse) {
        guard let id = e.agent_id else { return }
        let item = AgentItem(id: id, command: e.command ?? "", status: e.status ?? "running", message: e.message ?? "", lines: e.lines ?? [], elapsed: e.elapsed ?? 0)
        if let i = items.firstIndex(where: { $0.id == id }) { items[i] = item } else { items.append(item) }
        if item.status == "done" { NSSound(named: "Glass")?.play() }
        syncPanel()
    }

    func dismiss(_ id: Int) {
        items.removeAll { $0.id == id }
        syncPanel()
    }

    func stop(_ id: Int) {
        EngineClient.shared.run("stop agent \(id)", frontApp: nil) { _ in }
    }

    private func syncPanel() {
        if items.isEmpty { panel?.orderOut(nil); return }
        if panel == nil { panel = AgentPanel() }
        panel?.present(count: items.count)
    }
}

final class AgentPanel: NSPanel {
    init() {
        super.init(contentRect: NSRect(x: 0, y: 0, width: 330, height: 200), styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        isOpaque = false
        backgroundColor = .clear
        hasShadow = false
        level = .floating
        collectionBehavior = [.canJoinAllSpaces, .stationary, .ignoresCycle, .fullScreenAuxiliary]
        let host = NSHostingView(rootView: AgentListView())
        contentView = host
    }
    override var canBecomeKey: Bool { false }

    func present(count: Int) {
        guard let screen = NSScreen.main else { return }
        let h = min(CGFloat(count) * 108 + 16, 520)
        setFrame(NSRect(x: screen.visibleFrame.minX + 16, y: screen.visibleFrame.minY + 16, width: 330, height: h), display: true)
        orderFrontRegardless()
    }
}

struct AgentListView: View {
    private var center = AgentCenter.shared

    var body: some View {
        GlassEffectContainer(spacing: 8) {
            ScrollView {
                VStack(spacing: 8) {
                    ForEach(center.items) { item in AgentCard(item: item) }
                }
                .padding(8)
            }
        }
    }
}

struct AgentCard: View {
    let item: AgentItem

    private var color: Color {
        switch item.status {
        case "done": return .green
        case "failed": return .red
        case "needs_approval": return .orange
        case "stopped": return .gray
        default: return Module.assistant.tint
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack(spacing: 8) {
                if item.status == "running" {
                    ProgressView().controlSize(.small)
                } else {
                    Circle().fill(color).frame(width: 9, height: 9)
                }
                Text("Agent \(item.id)").font(.system(size: 11, weight: .semibold)).foregroundStyle(.secondary)
                Spacer()
                if item.status == "running" {
                    Button { AgentCenter.shared.stop(item.id) } label: { Image(systemName: "stop.fill") }
                        .buttonStyle(.plain).help("Stop")
                }
                Button { AgentCenter.shared.dismiss(item.id) } label: { Image(systemName: "xmark") }
                    .buttonStyle(.plain).help("Dismiss")
            }
            Text(item.command).font(.system(size: 12.5, weight: .medium)).lineLimit(2)
            ForEach(Array(item.lines.prefix(3).enumerated()), id: \.offset) { _, line in
                Text(line).font(.system(size: 11)).foregroundStyle(.secondary).lineLimit(1)
            }
            if !item.message.isEmpty, item.lines.isEmpty || item.status != "done" {
                Text(item.message).font(.system(size: 11)).foregroundStyle(color).lineLimit(2)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassEffect(.regular, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
    }
}
