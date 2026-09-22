import AppKit

enum ActiveGauge: Int {
    case none = -1
    case laya = 0
    case system = 1
    case assistant = 2
}

class CanvasView: NSView {
    weak var islandView: IslandView?

    override var isFlipped: Bool { true }

    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        islandView?.renderCanvas(dirtyRect: dirtyRect)
    }
}

class IslandView: NSView, NSTextFieldDelegate {
    var activeGauge: ActiveGauge = .laya
    var isHovered: Bool = true
    var isPinned: Bool = false

    var snapshot = SystemStats.shared.getSnapshot()
    var layaConfidence: Int = 94
    var assistantReadiness: Int = 52

    private var trackingArea: NSTrackingArea?
    private var inputField: NSTextField?
    private var micButton: NSButton?
    private var waveView: SpectrometerWaveView?
    private var voiceGlowView: VoiceGlowBeamView?
    private var thinkingOrbView: ThinkingOrbView?
    private var actionButtons: [NSButton] = []

    // Liquid Glass Blur Views
    private var islandBlur: NSVisualEffectView!
    private var popoverBlur: NSVisualEffectView!
    private var canvasView: CanvasView!

    // Layout Dimensions
    let islandWidth: CGFloat = 72
    let popoverWidth: CGFloat = 300
    let popoverHeight: CGFloat = 175
    let gap: CGFloat = 12

    var isDarkMode: Bool {
        if let match = effectiveAppearance.bestMatch(from: [.darkAqua, .aqua]) {
            return match == .darkAqua
        }
        return UserDefaults.standard.string(forKey: "AppleInterfaceStyle") == "Dark"
    }

    override var isFlipped: Bool { true }

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        setupLayers()
        setupInputControls()
        setupThemeObserver()
        setupHotKeyObserver()
        applyTheme()
    }

    required init?(coder: NSCoder) {
        super.init(coder: coder)
        setupLayers()
        setupInputControls()
        setupThemeObserver()
        setupHotKeyObserver()
        applyTheme()
    }

    deinit {
        DistributedNotificationCenter.default().removeObserver(self)
        NotificationCenter.default.removeObserver(self)
    }

    private func setupThemeObserver() {
        DistributedNotificationCenter.default().addObserver(
            self,
            selector: #selector(systemThemeChanged),
            name: NSNotification.Name("AppleInterfaceThemeChangedNotification"),
            object: nil
        )
    }

    private func setupHotKeyObserver() {
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(handleHotKeyToggle),
            name: NSNotification.Name("SpeedXToggleHotKey"),
            object: nil
        )
    }

    @objc private func handleHotKeyToggle() {
        if isHovered && activeGauge == .assistant && window?.isKeyWindow == true {
            // Hotkey toggles closed if already focused
            isHovered = false
            activeGauge = .none
            isPinned = false
            updateInteractiveControls()
            canvasView.needsDisplay = true
            window?.resignKey()
            return
        }

        // Open Assistant card and focus text input field
        activeGauge = .assistant
        isHovered = true
        isPinned = true
        updateInteractiveControls()
        canvasView.needsDisplay = true

        if let win = window {
            win.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            if let tf = inputField {
                win.makeFirstResponder(tf)
                tf.selectText(nil)
            }
        }
    }

    @objc private func systemThemeChanged() {
        DispatchQueue.main.async { [weak self] in
            self?.applyTheme()
        }
    }

    override func viewDidChangeEffectiveAppearance() {
        super.viewDidChangeEffectiveAppearance()
        applyTheme()
    }

    func applyTheme() {
        let dark = isDarkMode
        let appearanceName: NSAppearance.Name = dark ? .vibrantDark : .vibrantLight
        islandBlur?.appearance = NSAppearance(named: appearanceName)
        popoverBlur?.appearance = NSAppearance(named: appearanceName)

        // Update input field for light vs dark mode
        inputField?.textColor = dark ? .white : NSColor(calibratedWhite: 0.10, alpha: 1.0)
        inputField?.backgroundColor = dark ? NSColor(white: 1.0, alpha: 0.12) : NSColor(white: 1.0, alpha: 0.28)
        inputField?.layer?.borderColor = dark ? NSColor(white: 1.0, alpha: 0.25).cgColor : NSColor(white: 1.0, alpha: 0.65).cgColor

        // Update mic button
        if !(SpeechManager.shared.isRecording) {
            micButton?.layer?.backgroundColor = dark ? NSColor(white: 1.0, alpha: 0.15).cgColor : NSColor(white: 1.0, alpha: 0.30).cgColor
            micButton?.layer?.borderColor = dark ? NSColor(white: 1.0, alpha: 0.22).cgColor : NSColor(white: 1.0, alpha: 0.60).cgColor
            micButton?.contentTintColor = dark ? .white : NSColor(calibratedWhite: 0.12, alpha: 1.0)
        }

        // Update action buttons for light vs dark mode
        for btn in actionButtons {
            btn.layer?.backgroundColor = dark ? NSColor(white: 1.0, alpha: 0.15).cgColor : NSColor(white: 1.0, alpha: 0.30).cgColor
            btn.layer?.borderColor = dark ? NSColor(white: 1.0, alpha: 0.22).cgColor : NSColor(white: 1.0, alpha: 0.60).cgColor
            btn.contentTintColor = dark ? .white : NSColor(calibratedWhite: 0.12, alpha: 1.0)
        }

        waveView?.isDarkMode = dark
        thinkingOrbView?.isDarkMode = dark
        voiceGlowView?.isDarkMode = dark
        canvasView?.needsDisplay = true
    }

    private func setupLayers() {
        wantsLayer = true

        let dark = isDarkMode
        let initialAppearance = NSAppearance(named: dark ? .vibrantDark : .vibrantLight)

        // 1. Island Liquid Glass Backdrop (blurs underlying desktop/windows)
        islandBlur = NSVisualEffectView(frame: .zero)
        islandBlur.blendingMode = .behindWindow
        islandBlur.material = .popover
        islandBlur.state = .active
        islandBlur.appearance = initialAppearance
        islandBlur.wantsLayer = true
        addSubview(islandBlur)

        // 2. Popover Liquid Glass Backdrop
        popoverBlur = NSVisualEffectView(frame: .zero)
        popoverBlur.blendingMode = .behindWindow
        popoverBlur.material = .popover
        popoverBlur.state = .active
        popoverBlur.appearance = initialAppearance
        popoverBlur.wantsLayer = true
        addSubview(popoverBlur)

        // 3. Foreground Canvas View (sits ON TOP of the blur backdrops)
        canvasView = CanvasView(frame: bounds)
        canvasView.islandView = self
        canvasView.wantsLayer = true
        addSubview(canvasView)
    }

    private func setupInputControls() {
        // Voice-Glow Beam View along bottom of input box
        let vg = VoiceGlowBeamView(frame: NSRect(x: 16, y: 44, width: popoverWidth - 32, height: 34))
        vg.isDarkMode = isDarkMode
        vg.isHidden = true
        addSubview(vg)
        self.voiceGlowView = vg

        // Thinking Orb View (Libraries.dev thought-orb loading indicator)
        let orb = ThinkingOrbView(frame: NSRect(x: 20, y: 15, width: 22, height: 22))
        orb.isDarkMode = isDarkMode
        orb.state = .breathing
        orb.isHidden = true
        addSubview(orb)
        self.thinkingOrbView = orb

        let micW: CGFloat = 28
        let micGap: CGFloat = 6
        let inputW = popoverWidth - 40 - micW - micGap

        let tf = NSTextField(frame: NSRect(x: 20, y: 48, width: inputW, height: 28))
        tf.placeholderString = "Andika au sema... (e.g. ongeza sauti)"
        tf.font = NSFont.systemFont(ofSize: 11.5)
        tf.textColor = NSColor(calibratedWhite: 0.10, alpha: 1.0)
        tf.backgroundColor = NSColor(white: 1.0, alpha: 0.40)
        tf.isBordered = false
        tf.wantsLayer = true
        tf.layer?.cornerRadius = 8
        tf.layer?.borderWidth = 1.0
        tf.layer?.borderColor = NSColor(white: 1.0, alpha: 0.80).cgColor
        tf.focusRingType = .none
        tf.delegate = self
        tf.isHidden = true
        addSubview(tf)
        self.inputField = tf

        // Microphone Button
        let mic = NSButton(frame: NSRect(x: 20 + inputW + micGap, y: 48, width: micW, height: 28))
        mic.bezelStyle = .inline
        mic.isBordered = false
        mic.wantsLayer = true
        mic.layer?.cornerRadius = 8
        mic.layer?.borderWidth = 1.0
        mic.layer?.borderColor = NSColor(white: 1.0, alpha: 0.60).cgColor
        mic.layer?.backgroundColor = NSColor(white: 1.0, alpha: 0.30).cgColor
        if let sym = NSImage(systemSymbolName: "mic.fill", accessibilityDescription: "Record Audio") {
            let config = NSImage.SymbolConfiguration(pointSize: 12, weight: .bold)
            mic.image = sym.withSymbolConfiguration(config)
        }
        mic.imagePosition = .imageOnly
        mic.target = self
        mic.action = #selector(onMicButtonClicked(_:))
        mic.isHidden = true
        addSubview(mic)
        self.micButton = mic

        // Wire SpeechManager callbacks
        SpeechManager.shared.onSpeechPartial = { [weak self] partial in
            self?.inputField?.stringValue = partial
        }

        SpeechManager.shared.onSpeechFinished = { [weak self] text in
            guard let self = self else { return }
            let cmd = (self.inputField?.stringValue ?? text).trimmingCharacters(in: .whitespaces)
            if !cmd.isEmpty {
                self.triggerCommand(cmd)
                self.inputField?.stringValue = ""
            }
        }

        // Gemini Live Spectrometer Wave View
        let wv = SpectrometerWaveView(frame: NSRect(x: 20, y: 82, width: popoverWidth - 40, height: 30))
        wv.isDarkMode = isDarkMode
        wv.isHidden = true
        addSubview(wv)
        self.waveView = wv

        SpeechManager.shared.onAudioLevel = { [weak self] level in
            self?.waveView?.setAudioLevel(level)
            self?.voiceGlowView?.setAudioLevel(level)
        }

        SpeechManager.shared.onStateChange = { [weak self] isRecording in
            guard let self = self else { return }
            self.updateMicButtonAppearance(isRecording: isRecording)
            if isRecording {
                self.thinkingOrbView?.state = .listening
                self.voiceGlowView?.isProcessing = false
                self.waveView?.startAnimating()
            } else {
                self.waveView?.stopAnimating()
                if !(self.voiceGlowView?.isProcessing ?? false) {
                    self.thinkingOrbView?.state = .breathing
                }
            }
            self.updateInteractiveControls()
        }

        let actions: [(String, String, String)] = [
            ("Cheza", "play.fill", "cheza muziki"),
            ("Sauti+", "speaker.wave.2.fill", "ongeza sauti"),
            ("Kioo", "display", "read screen"),
            ("Nakili", "doc.on.clipboard", "inspect clipboard")
        ]

        let btnWidth: CGFloat = (popoverWidth - 40 - 18) / 4
        for (i, (label, iconName, cmd)) in actions.enumerated() {
            let btn = NSButton(frame: NSRect(x: 20 + CGFloat(i) * (btnWidth + 6), y: 84, width: btnWidth, height: 26))
            btn.title = label
            if let sym = NSImage(systemSymbolName: iconName, accessibilityDescription: label) {
                let config = NSImage.SymbolConfiguration(pointSize: 9.5, weight: .semibold)
                btn.image = sym.withSymbolConfiguration(config)
                btn.imagePosition = .imageLeading
                btn.imageScaling = .scaleProportionallyDown
            }
            btn.bezelStyle = .inline
            btn.isBordered = false
            btn.wantsLayer = true
            btn.layer?.backgroundColor = NSColor(white: 1.0, alpha: 0.45).cgColor
            btn.layer?.cornerRadius = 7
            btn.layer?.borderWidth = 1.0
            btn.layer?.borderColor = NSColor(white: 1.0, alpha: 0.75).cgColor
            btn.contentTintColor = NSColor(calibratedWhite: 0.12, alpha: 1.0)
            btn.font = NSFont.systemFont(ofSize: 10, weight: .semibold)
            btn.target = self
            btn.action = #selector(onActionButtonClicked(_:))
            btn.identifier = NSUserInterfaceItemIdentifier(cmd)
            btn.isHidden = true
            addSubview(btn)
            actionButtons.append(btn)
        }
    }

    @objc private func onMicButtonClicked(_ sender: NSButton) {
        SpeechManager.shared.toggleRecording()
    }

    private func updateMicButtonAppearance(isRecording: Bool) {
        let dark = isDarkMode
        if isRecording {
            micButton?.layer?.backgroundColor = NSColor.systemRed.withAlphaComponent(0.35).cgColor
            micButton?.layer?.borderColor = NSColor.systemRed.cgColor
            micButton?.contentTintColor = .systemRed
            if let sym = NSImage(systemSymbolName: "record.circle.fill", accessibilityDescription: "Recording") {
                let config = NSImage.SymbolConfiguration(pointSize: 12, weight: .bold)
                micButton?.image = sym.withSymbolConfiguration(config)
            }
            inputField?.placeholderString = "Listening... sema sasa..."
        } else {
            micButton?.layer?.backgroundColor = dark ? NSColor(white: 1.0, alpha: 0.15).cgColor : NSColor(white: 1.0, alpha: 0.30).cgColor
            micButton?.layer?.borderColor = dark ? NSColor(white: 1.0, alpha: 0.22).cgColor : NSColor(white: 1.0, alpha: 0.60).cgColor
            micButton?.contentTintColor = dark ? .white : NSColor(calibratedWhite: 0.12, alpha: 1.0)
            if let sym = NSImage(systemSymbolName: "mic.fill", accessibilityDescription: "Record Audio") {
                let config = NSImage.SymbolConfiguration(pointSize: 12, weight: .bold)
                micButton?.image = sym.withSymbolConfiguration(config)
            }
            inputField?.placeholderString = "Andika au sema... (e.g. ongeza sauti)"
        }
        canvasView.needsDisplay = true
    }

    @objc private func onActionButtonClicked(_ sender: NSButton) {
        if let cmd = sender.identifier?.rawValue {
            triggerCommand(cmd)
        }
    }

    func control(_ control: NSControl, textView: NSTextView, doCommandBy commandSelector: Selector) -> Bool {
        if commandSelector == #selector(insertNewline(_:)) {
            let text = inputField?.stringValue.trimmingCharacters(in: .whitespaces) ?? ""
            if !text.isEmpty {
                triggerCommand(text)
                inputField?.stringValue = ""
            }
            return true
        }
        return false
    }

    private func triggerCommand(_ cmd: String) {
        voiceGlowView?.isProcessing = true
        thinkingOrbView?.state = .working
        inputField?.stringValue = ""
        SpeedXRunner.shared.execute(command: cmd) { [weak self] _ in
            DispatchQueue.main.async {
                self?.voiceGlowView?.isProcessing = false
                self?.thinkingOrbView?.state = .breathing
                self?.canvasView.needsDisplay = true
            }
        }
    }

    func updateMetrics() {
        self.snapshot = SystemStats.shared.getSnapshot()
        self.canvasView.needsDisplay = true
    }

    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        if let ta = trackingArea { removeTrackingArea(ta) }
        let ta = NSTrackingArea(rect: bounds, options: [.mouseEnteredAndExited, .mouseMoved, .activeAlways], owner: self, userInfo: nil)
        addTrackingArea(ta)
        self.trackingArea = ta
    }

    // MARK: - Mouse Events
    override func mouseEntered(with event: NSEvent) {
        isHovered = true
        canvasView.needsDisplay = true
    }

    override func mouseExited(with event: NSEvent) {
        if !isPinned {
            isHovered = false
            activeGauge = .none
            updateInteractiveControls()
            canvasView.needsDisplay = true
        }
    }

    override func mouseMoved(with event: NSEvent) {
        let loc = convert(event.locationInWindow, from: nil)
        let rightX = bounds.maxX - islandWidth

        if loc.x >= rightX {
            let islandTop: CGFloat = 20
            let gaugeSpacing: CGFloat = 86
            let gauge1Y = islandTop + 54
            let gauge2Y = gauge1Y + gaugeSpacing
            let gauge3Y = gauge2Y + gaugeSpacing

            let prev = activeGauge
            if abs(loc.y - gauge1Y) < 38 {
                activeGauge = .laya
            } else if abs(loc.y - gauge2Y) < 38 {
                activeGauge = .system
            } else if abs(loc.y - gauge3Y) < 38 {
                activeGauge = .assistant
            }

            if prev != activeGauge {
                isHovered = true
                updateInteractiveControls()
                canvasView.needsDisplay = true
            }
        }
    }

    override func acceptsFirstMouse(for event: NSEvent?) -> Bool {
        return true
    }

    override func mouseDown(with event: NSEvent) {
        let loc = convert(event.locationInWindow, from: nil)
        let rightX = bounds.maxX - islandWidth

        if loc.x >= rightX {
            let islandTop: CGFloat = 20
            let gaugeSpacing: CGFloat = 86
            let gauge1Y = islandTop + 54
            let gauge2Y = gauge1Y + gaugeSpacing
            let gauge3Y = gauge2Y + gaugeSpacing

            if abs(loc.y - gauge1Y) < 38 {
                activeGauge = .laya
            } else if abs(loc.y - gauge2Y) < 38 {
                activeGauge = .system
            } else if abs(loc.y - gauge3Y) < 38 {
                activeGauge = .assistant
            }
            isHovered = true
            isPinned = true
            updateInteractiveControls()
            canvasView.needsDisplay = true
            return
        }

        // Check if micButton was clicked
        if let mic = micButton, !mic.isHidden, mic.frame.contains(loc) {
            SpeechManager.shared.toggleRecording()
            return
        }

        // Check if waveView was clicked (to stop recording)
        if let wv = waveView, !wv.isHidden, wv.frame.contains(loc) {
            SpeechManager.shared.toggleRecording()
            return
        }

        // Check action buttons
        for btn in actionButtons {
            if !btn.isHidden && btn.frame.contains(loc) {
                if let cmd = btn.identifier?.rawValue {
                    triggerCommand(cmd)
                }
                return
            }
        }
    }

    private func updateInteractiveControls() {
        let showAssistantControls = (activeGauge == .assistant && isHovered)
        let isRecording = SpeechManager.shared.isRecording

        inputField?.isHidden = !showAssistantControls
        micButton?.isHidden = !showAssistantControls
        voiceGlowView?.isHidden = !showAssistantControls
        thinkingOrbView?.isHidden = !showAssistantControls

        if isRecording {
            thinkingOrbView?.state = .listening
        } else if !(voiceGlowView?.isProcessing ?? false) {
            thinkingOrbView?.state = .breathing
        }

        // When recording: show Gemini Live Spectrometer Wave, hide quick actions
        waveView?.isHidden = !(showAssistantControls && isRecording)
        for btn in actionButtons {
            btn.isHidden = !(showAssistantControls && !isRecording)
        }
    }

    // MARK: - Geometry & Mask Generation
    private func updateGlassBackdrops(islandRect: NSRect, cardRect: NSRect, arrowY: CGFloat) {
        canvasView.frame = bounds

        // 1. Position and Mask Island Blur
        islandBlur.frame = islandRect
        let islandPath = IslandShape.createPath(in: NSRect(origin: .zero, size: islandRect.size), width: islandWidth, topFillet: 38, bottomFillet: 38)
        islandBlur.maskImage = NSImage(size: islandRect.size, flipped: true) { _ in
            NSColor.black.setFill()
            islandPath.fill()
            return true
        }

        // 2. Position and Mask Popover Blur
        if isHovered && activeGauge != .none {
            popoverBlur.isHidden = false
            popoverBlur.frame = cardRect
            let localArrowY = arrowY - cardRect.minY
            let cardPath = IslandShape.createPopoverPath(in: NSRect(origin: .zero, size: cardRect.size), arrowY: localArrowY, cornerRadius: 18)
            popoverBlur.maskImage = NSImage(size: cardRect.size, flipped: true) { _ in
                NSColor.black.setFill()
                cardPath.fill()
                return true
            }

            let micW: CGFloat = 28
            let micGap: CGFloat = 6
            let inputW = popoverWidth - 40 - micW - micGap
            inputField?.frame = NSRect(x: cardRect.minX + 20, y: cardRect.minY + 48, width: inputW, height: 28)
            micButton?.frame = NSRect(x: cardRect.minX + 20 + inputW + micGap, y: cardRect.minY + 48, width: micW, height: 28)
            voiceGlowView?.frame = NSRect(x: cardRect.minX + 16, y: cardRect.minY + 44, width: popoverWidth - 32, height: 34)
            thinkingOrbView?.frame = NSRect(x: cardRect.minX + 20, y: cardRect.minY + 15, width: 22, height: 22)
            waveView?.frame = NSRect(x: cardRect.minX + 20, y: cardRect.minY + 84, width: popoverWidth - 40, height: 28)

            let btnWidth: CGFloat = (popoverWidth - 40 - 18) / 4
            for (i, btn) in actionButtons.enumerated() {
                btn.frame = NSRect(x: cardRect.minX + 20 + CGFloat(i) * (btnWidth + 6), y: cardRect.minY + 84, width: btnWidth, height: 26)
            }
        } else {
            popoverBlur.isHidden = true
        }
    }

    // MARK: - Rendering on Top of Liquid Glass
    func renderCanvas(dirtyRect: NSRect) {
        guard let ctx = NSGraphicsContext.current?.cgContext else { return }

        let w = bounds.width
        let islandRight = w
        let islandLeft = islandRight - islandWidth
        let islandTop: CGFloat = 20
        let islandBottom: CGFloat = 345

        let islandRect = NSRect(x: islandLeft, y: islandTop, width: islandWidth, height: islandBottom - islandTop)

        let gaugeCenterX = islandLeft + (islandWidth / 2) + 2
        let gauge1CenterY: CGFloat = islandTop + 54
        let gauge2CenterY: CGFloat = gauge1CenterY + 86
        let gauge3CenterY: CGFloat = gauge2CenterY + 86

        var targetArrowY: CGFloat = gauge1CenterY
        if activeGauge == .system { targetArrowY = gauge2CenterY }
        else if activeGauge == .assistant { targetArrowY = gauge3CenterY }

        let popoverX = bounds.maxX - islandWidth - gap - popoverWidth
        let popoverY = max(10, min(bounds.height - popoverHeight - 10, targetArrowY - popoverHeight / 2))
        let cardRect = NSRect(x: popoverX, y: popoverY, width: popoverWidth, height: popoverHeight)

        // Update glass backdrops below canvas
        updateGlassBackdrops(islandRect: islandRect, cardRect: cardRect, arrowY: targetArrowY)

        let dark = isDarkMode

        // 1. Draw Transparent Glassmorphic Island Surface
        // Light mode: white bg with 25% opacity!
        // Dark mode: translucent dark glass with 25% opacity!
        let islandPath = IslandShape.createPath(in: islandRect, width: islandWidth, topFillet: 38, bottomFillet: 38)
        ctx.saveGState()
        let islandSurface = dark ? NSColor(calibratedRed: 16/255, green: 18/255, blue: 24/255, alpha: 0.25)
                                 : NSColor(calibratedWhite: 1.0, alpha: 0.25)
        islandSurface.setFill()
        islandPath.fill()

        // Specular Refraction Rim (Liquid glass highlight)
        let islandRim = dark ? NSColor(calibratedWhite: 1.0, alpha: 0.35)
                             : NSColor(calibratedWhite: 1.0, alpha: 0.85)
        islandRim.setStroke()
        islandPath.lineWidth = 1.2
        islandPath.stroke()
        ctx.restoreGState()

        // 2. Draw Gauges & Control Rings
        drawGauge(ctx: ctx, center: CGPoint(x: gaugeCenterX, y: gauge1CenterY), pct: layaConfidence, ringColor: NSColor(calibratedRed: 255/255, green: 107/255, blue: 53/255, alpha: 1.0), iconType: 0, label: "\(layaConfidence)%")
        drawGauge(ctx: ctx, center: CGPoint(x: gaugeCenterX, y: gauge2CenterY), pct: snapshot.ramPercentage, ringColor: NSColor(calibratedRed: 16/255, green: 185/255, blue: 129/255, alpha: 1.0), iconType: 1, label: "\(snapshot.ramPercentage)%")
        drawGauge(ctx: ctx, center: CGPoint(x: gaugeCenterX, y: gauge3CenterY), pct: assistantReadiness, ringColor: dark ? NSColor(calibratedRed: 212/255, green: 225/255, blue: 87/255, alpha: 1.0) : NSColor(calibratedRed: 100/255, green: 175/255, blue: 25/255, alpha: 1.0), iconType: 2, label: "\(assistantReadiness)%")

        // 3. Draw Popover Glass Overlays & Content
        if isHovered && activeGauge != .none {
            let cardPath = IslandShape.createPopoverPath(in: cardRect, arrowY: targetArrowY, cornerRadius: 18)

            ctx.saveGState()
            // Ambient soft drop shadow
            let shadowColor = dark ? NSColor(white: 0, alpha: 0.40) : NSColor(calibratedWhite: 0.1, alpha: 0.16)
            ctx.setShadow(offset: CGSize(width: -6, height: 10), blur: 22, color: shadowColor.cgColor)

            // Transparent glassmorphism fill (25% opacity in light mode)
            let popoverSurface = dark ? NSColor(calibratedRed: 16/255, green: 18/255, blue: 24/255, alpha: 0.25)
                                      : NSColor(calibratedWhite: 1.0, alpha: 0.25)
            popoverSurface.setFill()
            cardPath.fill()

            // Specular border
            let popoverRim = dark ? NSColor(calibratedWhite: 1.0, alpha: 0.35)
                                  : NSColor(calibratedWhite: 1.0, alpha: 0.85)
            popoverRim.setStroke()
            cardPath.lineWidth = 1.2
            cardPath.stroke()
            ctx.restoreGState()

            // Control Center style frosted modules inside the card
            switch activeGauge {
            case .laya:
                renderLayaGlassCard(in: cardRect)
            case .system:
                renderSystemGlassCard(in: cardRect)
            case .assistant:
                renderAssistantGlassCard(in: cardRect)
            default:
                break
            }
        }
    }

    // MARK: - Draw Circular Gauge with Liquid Glass Badge
    private func drawGauge(ctx: CGContext, center: CGPoint, pct: Int, ringColor: NSColor, iconType: Int, label: String) {
        let radius: CGFloat = 20
        let ringThickness: CGFloat = 3.2
        let dark = isDarkMode

        // Background glass trough
        ctx.saveGState()
        let troughColor = dark ? NSColor(calibratedWhite: 1.0, alpha: 0.12) : NSColor(calibratedWhite: 0.0, alpha: 0.12)
        ctx.setStrokeColor(troughColor.cgColor)
        ctx.setLineWidth(ringThickness)
        ctx.addArc(center: center, radius: radius, startAngle: 0, endAngle: .pi * 2, clockwise: false)
        ctx.strokePath()

        // Active glowing progress arc
        let startAngle: CGFloat = -.pi / 2
        let endAngle: CGFloat = startAngle + (CGFloat(pct) / 100.0) * (.pi * 2)

        ctx.setStrokeColor(ringColor.cgColor)
        ctx.setLineWidth(ringThickness)
        ctx.setLineCap(.round)
        ctx.addArc(center: center, radius: radius, startAngle: startAngle, endAngle: endAngle, clockwise: false)
        ctx.strokePath()

        // Frosted Glass Inner Badge
        let innerRadius = radius - ringThickness - 1.5
        let badgeColor = dark ? NSColor(calibratedWhite: 0.18, alpha: 0.70) : NSColor(calibratedWhite: 1.0, alpha: 0.80)
        ctx.setFillColor(badgeColor.cgColor)
        ctx.addArc(center: center, radius: innerRadius, startAngle: 0, endAngle: .pi * 2, clockwise: false)
        ctx.fillPath()

        // Specular inner ring highlight
        let badgeRim = dark ? NSColor(calibratedWhite: 1.0, alpha: 0.22) : NSColor(calibratedWhite: 1.0, alpha: 0.95)
        ctx.setStrokeColor(badgeRim.cgColor)
        ctx.setLineWidth(1.0)
        ctx.addArc(center: center, radius: innerRadius, startAngle: 0, endAngle: .pi * 2, clockwise: false)
        ctx.strokePath()

        // Center vector icon
        drawCustomIcon(ctx: ctx, center: center, type: iconType, isDark: dark)

        // Percentage text below gauge
        let lblStr = NSString(string: label)
        let labelColor = dark ? NSColor.white : NSColor(calibratedWhite: 0.12, alpha: 1.0)
        let lblAttrs: [NSAttributedString.Key: Any] = [
            .font: NSFont.systemFont(ofSize: 11, weight: .bold),
            .foregroundColor: labelColor
        ]
        let lblSize = lblStr.size(withAttributes: lblAttrs)
        let lblRect = NSRect(x: center.x - lblSize.width / 2, y: center.y + radius + 5, width: lblSize.width, height: lblSize.height)
        lblStr.draw(in: lblRect, withAttributes: lblAttrs)

        ctx.restoreGState()
    }

    private func drawCustomIcon(ctx: CGContext, center: CGPoint, type: Int, isDark: Bool) {
        ctx.saveGState()
        let strokeColor = isDark ? NSColor.white : NSColor(calibratedWhite: 0.15, alpha: 1.0)
        ctx.setStrokeColor(strokeColor.cgColor)
        ctx.setLineCap(.round)
        ctx.setLineJoin(.round)

        if type == 0 {
            // Claude Starburst
            ctx.setLineWidth(1.6)
            for i in 0..<8 {
                let angle = (Double(i) * .pi / 4.0) + (.pi / 8.0)
                let rInner: CGFloat = 2.6
                let rOuter: CGFloat = 7.5
                let x1 = center.x + CGFloat(cos(angle)) * rInner
                let y1 = center.y + CGFloat(sin(angle)) * rInner
                let x2 = center.x + CGFloat(cos(angle)) * rOuter
                let y2 = center.y + CGFloat(sin(angle)) * rOuter
                ctx.move(to: CGPoint(x: x1, y: y1))
                ctx.addLine(to: CGPoint(x: x2, y: y2))
            }
            ctx.strokePath()
        } else if type == 1 {
            // Spiral Vortex
            ctx.setLineWidth(1.4)
            for i in 0..<6 {
                let angle = Double(i) * (.pi / 3.0)
                let r: CGFloat = 6.4
                let p1 = CGPoint(x: center.x + CGFloat(cos(angle)) * 2.0, y: center.y + CGFloat(sin(angle)) * 2.0)
                let p2 = CGPoint(x: center.x + CGFloat(cos(angle + 0.55)) * r, y: center.y + CGFloat(sin(angle + 0.55)) * r)
                ctx.move(to: p1)
                ctx.addLine(to: p2)
            }
            ctx.strokePath()
            ctx.addArc(center: center, radius: 2.0, startAngle: 0, endAngle: .pi * 2, clockwise: false)
            ctx.strokePath()
        } else {
            // Neural Node Snowflake
            ctx.setLineWidth(1.4)
            for i in 0..<4 {
                let angle = Double(i) * (.pi / 4.0)
                let r: CGFloat = 7.0
                let x1 = center.x + CGFloat(cos(angle)) * r
                let y1 = center.y + CGFloat(sin(angle)) * r
                let x2 = center.x - CGFloat(cos(angle)) * r
                let y2 = center.y - CGFloat(sin(angle)) * r
                ctx.move(to: CGPoint(x: x1, y: y1))
                ctx.addLine(to: CGPoint(x: x2, y: y2))
            }
            ctx.strokePath()
            ctx.setFillColor(strokeColor.cgColor)
            ctx.addArc(center: center, radius: 1.6, startAngle: 0, endAngle: .pi * 2, clockwise: false)
            ctx.fillPath()
        }
        ctx.restoreGState()
    }

    // MARK: - Control Center Style Frosted Glass Modules
    private func renderLayaGlassCard(in rect: NSRect) {
        let padX = rect.minX + 18
        var curY = rect.minY + 16
        let dark = isDarkMode

        let primaryText = dark ? NSColor.white : NSColor(calibratedWhite: 0.10, alpha: 1.0)
        let secText = dark ? NSColor(white: 0.65, alpha: 1.0) : NSColor(calibratedWhite: 0.38, alpha: 1.0)
        let subText = dark ? NSColor(white: 0.85, alpha: 1.0) : NSColor(calibratedWhite: 0.25, alpha: 1.0)

        drawGlassHeader(iconName: "sparkles", title: "Speed-X CoreML Engine", at: CGPoint(x: padX, y: curY))
        curY += 26

        let mod1Rect = NSRect(x: padX, y: curY, width: popoverWidth - 48, height: 50)
        drawFrostedPillModule(in: mod1Rect)
        drawText("Current Decision", at: CGPoint(x: mod1Rect.minX + 12, y: mod1Rect.minY + 8), font: .boldSystemFont(ofSize: 11), color: primaryText)
        drawText("Latency: ~190ms", at: CGPoint(x: mod1Rect.maxX - 110, y: mod1Rect.minY + 8), font: .systemFont(ofSize: 10), color: secText)
        drawControlCenterSlider(x: mod1Rect.minX + 12, y: mod1Rect.minY + 26, width: mod1Rect.width - 24, pct: layaConfidence, color: NSColor(calibratedRed: 255/255, green: 107/255, blue: 53/255, alpha: 1.0))
        drawText("\(layaConfidence)% Confidence (High)", at: CGPoint(x: mod1Rect.minX + 12, y: mod1Rect.minY + 36), font: .boldSystemFont(ofSize: 9.5), color: subText)

        curY += 58

        let mod2Rect = NSRect(x: padX, y: curY, width: popoverWidth - 48, height: 50)
        drawFrostedPillModule(in: mod2Rect)
        drawText("Engine: Intel i5 CoreML", at: CGPoint(x: mod2Rect.minX + 12, y: mod2Rect.minY + 8), font: .boldSystemFont(ofSize: 11), color: primaryText)
        drawText("compute: cpu", at: CGPoint(x: mod2Rect.maxX - 95, y: mod2Rect.minY + 8), font: .systemFont(ofSize: 10), color: secText)
        drawControlCenterSlider(x: mod2Rect.minX + 12, y: mod2Rect.minY + 26, width: mod2Rect.width - 24, pct: 15, color: NSColor(calibratedRed: 16/255, green: 185/255, blue: 129/255, alpha: 1.0))
        drawText("100% Offline · Zero Cloud Latency", at: CGPoint(x: mod2Rect.minX + 12, y: mod2Rect.minY + 36), font: .boldSystemFont(ofSize: 9.5), color: subText)
    }

    private func renderSystemGlassCard(in rect: NSRect) {
        let padX = rect.minX + 18
        var curY = rect.minY + 16
        let dark = isDarkMode

        let primaryText = dark ? NSColor.white : NSColor(calibratedWhite: 0.10, alpha: 1.0)
        let secText = dark ? NSColor(white: 0.65, alpha: 1.0) : NSColor(calibratedWhite: 0.38, alpha: 1.0)
        let subText = dark ? NSColor(white: 0.85, alpha: 1.0) : NSColor(calibratedWhite: 0.25, alpha: 1.0)

        drawGlassHeader(iconName: "gearshape.fill", title: "System Resources", at: CGPoint(x: padX, y: curY))
        curY += 26

        let ramRect = NSRect(x: padX, y: curY, width: popoverWidth - 48, height: 50)
        drawFrostedPillModule(in: ramRect)
        drawText("RAM Usage", at: CGPoint(x: ramRect.minX + 12, y: ramRect.minY + 8), font: .boldSystemFont(ofSize: 11), color: primaryText)
        drawText("\(snapshot.ramUsedGB) GB / \(snapshot.ramTotalGB) GB", at: CGPoint(x: ramRect.maxX - 125, y: ramRect.minY + 8), font: .systemFont(ofSize: 10), color: secText)
        drawControlCenterSlider(x: ramRect.minX + 12, y: ramRect.minY + 26, width: ramRect.width - 24, pct: snapshot.ramPercentage, color: NSColor(calibratedRed: 16/255, green: 185/255, blue: 129/255, alpha: 1.0))
        drawText("\(snapshot.ramPercentage)% Used", at: CGPoint(x: ramRect.minX + 12, y: ramRect.minY + 36), font: .boldSystemFont(ofSize: 9.5), color: subText)

        curY += 58

        let cpuRect = NSRect(x: padX, y: curY, width: popoverWidth - 48, height: 50)
        drawFrostedPillModule(in: cpuRect)
        drawText("Active App: \(snapshot.frontmostApp)", at: CGPoint(x: cpuRect.minX + 12, y: cpuRect.minY + 8), font: .boldSystemFont(ofSize: 11), color: primaryText)
        drawText("CPU: \(snapshot.cpuPercentage)%", at: CGPoint(x: cpuRect.maxX - 90, y: cpuRect.minY + 8), font: .systemFont(ofSize: 10), color: secText)
        drawControlCenterSlider(x: cpuRect.minX + 12, y: cpuRect.minY + 26, width: cpuRect.width - 24, pct: snapshot.cpuPercentage, color: NSColor(calibratedRed: 6/255, green: 182/255, blue: 212/255, alpha: 1.0))
        drawText("Hotkey: ⌥+Space · Login: Auto", at: CGPoint(x: cpuRect.minX + 12, y: cpuRect.minY + 36), font: .boldSystemFont(ofSize: 9.5), color: subText)
    }

    private func renderAssistantGlassCard(in rect: NSRect) {
        let padX = rect.minX + 18
        let curY = rect.minY + 16
        let dark = isDarkMode

        let primaryText = dark ? NSColor.white : NSColor(calibratedWhite: 0.10, alpha: 1.0)
        let secText = dark ? NSColor(white: 0.65, alpha: 1.0) : NSColor(calibratedWhite: 0.38, alpha: 1.0)

        // Title text is offset so thinkingOrbView sits at (padX, curY - 2, 22, 22)
        drawText("Speed-X Assistant", at: CGPoint(x: padX + 28, y: curY + 2), font: .boldSystemFont(ofSize: 13), color: primaryText)
        drawText("EN • SW", at: CGPoint(x: rect.maxX - 70, y: curY + 4), font: .systemFont(ofSize: 10, weight: .medium), color: secText)

        if voiceGlowView?.isProcessing == true {
            let workingColor = dark ? NSColor(calibratedRed: 0, green: 229/255, blue: 255/255, alpha: 1.0)
                                    : NSColor(calibratedRed: 0, green: 122/255, blue: 255/255, alpha: 1.0)
            if let img = NSImage(systemSymbolName: "sparkles", accessibilityDescription: nil) {
                let config = NSImage.SymbolConfiguration(pointSize: 11, weight: .semibold).applying(.init(paletteColors: [workingColor]))
                if let configured = img.withSymbolConfiguration(config) {
                    let iconRect = NSRect(x: padX + 4, y: rect.minY + 120, width: 14, height: 14)
                    configured.draw(in: iconRect, from: .zero, operation: .sourceOver, fraction: 1.0)
                }
            }
            drawText("Speed-X Engine Working...", at: CGPoint(x: padX + 22, y: rect.minY + 120), font: .systemFont(ofSize: 10, weight: .medium), color: workingColor)
        } else if let last = SpeedXRunner.shared.lastResponse {
            let iconSymbol = last.success ? "checkmark.circle.fill" : "exclamationmark.triangle.fill"
            let statusColor = last.success
                ? (dark ? NSColor(calibratedRed: 74/255, green: 222/255, blue: 128/255, alpha: 1.0) : NSColor(calibratedRed: 22/255, green: 135/255, blue: 60/255, alpha: 1.0))
                : (dark ? NSColor(calibratedRed: 251/255, green: 191/255, blue: 36/255, alpha: 1.0) : NSColor(calibratedRed: 217/255, green: 119/255, blue: 6/255, alpha: 1.0))

            if let img = NSImage(systemSymbolName: iconSymbol, accessibilityDescription: nil) {
                let config = NSImage.SymbolConfiguration(pointSize: 11, weight: .semibold).applying(.init(paletteColors: [statusColor]))
                if let configured = img.withSymbolConfiguration(config) {
                    let iconRect = NSRect(x: padX + 4, y: rect.minY + 120, width: 14, height: 14)
                    configured.draw(in: iconRect, from: .zero, operation: .sourceOver, fraction: 1.0)
                }
            }
            drawText(last.message, at: CGPoint(x: padX + 22, y: rect.minY + 120), font: .systemFont(ofSize: 10), color: statusColor)
        }
    }

    private func drawGlassHeader(iconName: String, title: String, at point: CGPoint) {
        let dark = isDarkMode
        let headerColor = dark ? NSColor.white : NSColor(calibratedWhite: 0.10, alpha: 1.0)

        if let icon = NSImage(systemSymbolName: iconName, accessibilityDescription: nil) {
            let config = NSImage.SymbolConfiguration(pointSize: 13, weight: .bold).applying(.init(paletteColors: [headerColor]))
            if let configured = icon.withSymbolConfiguration(config) {
                let iconRect = NSRect(x: point.x, y: point.y + 1, width: 16, height: 16)
                configured.draw(in: iconRect, from: .zero, operation: .sourceOver, fraction: 1.0)
            }
        }
        drawText(title, at: CGPoint(x: point.x + 22, y: point.y), font: .boldSystemFont(ofSize: 13), color: headerColor)
    }

    private func drawFrostedPillModule(in rect: NSRect) {
        let dark = isDarkMode
        let path = NSBezierPath(roundedRect: rect, xRadius: 13, yRadius: 13)
        let fill = dark ? NSColor(calibratedWhite: 1.0, alpha: 0.10) : NSColor(calibratedWhite: 1.0, alpha: 0.25)
        fill.setFill()
        path.fill()
        let stroke = dark ? NSColor(calibratedWhite: 1.0, alpha: 0.20) : NSColor(calibratedWhite: 1.0, alpha: 0.60)
        stroke.setStroke()
        path.lineWidth = 1.0
        path.stroke()
    }

    private func drawControlCenterSlider(x: CGFloat, y: CGFloat, width: CGFloat, pct: Int, color: NSColor) {
        let dark = isDarkMode
        let h: CGFloat = 8.0
        let trough = NSRect(x: x, y: y, width: width, height: h)
        let troughPath = NSBezierPath(roundedRect: trough, xRadius: h/2, yRadius: h/2)
        let trackColor = dark ? NSColor(calibratedWhite: 0.0, alpha: 0.35) : NSColor(calibratedWhite: 0.0, alpha: 0.10)
        trackColor.setFill()
        troughPath.fill()
        let trackStroke = dark ? NSColor(calibratedWhite: 1.0, alpha: 0.12) : NSColor(calibratedWhite: 1.0, alpha: 0.40)
        trackStroke.setStroke()
        troughPath.lineWidth = 0.5
        troughPath.stroke()

        let filledW = max(h, width * (CGFloat(min(100, max(0, pct))) / 100.0))
        let filled = NSRect(x: x, y: y, width: filledW, height: h)
        let filledPath = NSBezierPath(roundedRect: filled, xRadius: h/2, yRadius: h/2)
        color.setFill()
        filledPath.fill()
    }

    private func drawText(_ text: String, at point: CGPoint, font: NSFont, color: NSColor) {
        let str = NSString(string: text)
        let attrs: [NSAttributedString.Key: Any] = [
            .font: font,
            .foregroundColor: color
        ]
        str.draw(at: point, withAttributes: attrs)
    }
}
