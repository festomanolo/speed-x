import Cocoa

public class VoiceGlowBeamView: NSView {
    public var isProcessing: Bool = false {
        didSet {
            if oldValue != isProcessing {
                needsDisplay = true
            }
        }
    }
    public var isDarkMode: Bool = true {
        didSet { needsDisplay = true }
    }
    public var sensitivity: Double = 3.1
    public var threshold: Double = 0.015
    public var idle: Double = 0.23
    public var reach: Double = 1.25
    public var spread: Double = 1.05
    public var processingDuration: Double = 1.1

    private var targetLevel: Double = 0.0
    private var currentLevel: Double = 0.0
    private var clockTime: Double = 0.0
    private var lastTimestamp: Double = CACurrentMediaTime()
    private var animationTimer: Timer?

    // 7 lobes as defined in voice-glow
    private struct LobeConfig {
        let xOffsetRatio: Double // fraction of width/2
        let width: Double
        let height: Double
        let color: NSColor
    }

    private let lobes: [LobeConfig] = [
        LobeConfig(xOffsetRatio: -0.75, width: 42, height: 26, color: NSColor(red: 255/255, green: 70/255, blue: 120/255, alpha: 1.0)),
        LobeConfig(xOffsetRatio: -0.50, width: 48, height: 32, color: NSColor(red: 60/255, green: 190/255, blue: 255/255, alpha: 1.0)),
        LobeConfig(xOffsetRatio: -0.25, width: 54, height: 40, color: NSColor(red: 175/255, green: 70/255, blue: 255/255, alpha: 1.0)),
        LobeConfig(xOffsetRatio: 0.0,   width: 74, height: 46, color: NSColor(red: 60/255, green: 220/255, blue: 130/255, alpha: 1.0)),
        LobeConfig(xOffsetRatio: 0.25,  width: 54, height: 40, color: NSColor(red: 255/255, green: 150/255, blue: 40/255, alpha: 1.0)),
        LobeConfig(xOffsetRatio: 0.50,  width: 48, height: 32, color: NSColor(red: 90/255, green: 100/255, blue: 255/255, alpha: 1.0)),
        LobeConfig(xOffsetRatio: 0.75,  width: 42, height: 26, color: NSColor(red: 40/255, green: 200/255, blue: 190/255, alpha: 1.0))
    ]

    public override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        setup()
    }

    public required init?(coder: NSCoder) {
        super.init(coder: coder)
        setup()
    }

    private func setup() {
        wantsLayer = true
        layer?.backgroundColor = NSColor.clear.cgColor
        startAnimation()
    }

    public func setAudioLevel(_ level: Double) {
        let gated = level < threshold ? 0.0 : level * sensitivity
        targetLevel = min(1.0, max(0.0, gated))
    }

    public func setAudioLevel(_ level: Float) {
        setAudioLevel(Double(level))
    }

    public func startAnimation() {
        guard animationTimer == nil else { return }
        lastTimestamp = CACurrentMediaTime()
        animationTimer = Timer.scheduledTimer(withTimeInterval: 1.0 / 60.0, repeats: true) { [weak self] _ in
            guard let self = self else { return }
            let now = CACurrentMediaTime()
            let dt = min(0.05, now - self.lastTimestamp)
            self.lastTimestamp = now
            self.clockTime += dt

            // Envelope follower (attack = 0.325, release = 0.86)
            if self.targetLevel > self.currentLevel {
                let attackSpeed = dt / 0.325
                self.currentLevel += (self.targetLevel - self.currentLevel) * min(1.0, attackSpeed * 2.5)
            } else {
                let releaseSpeed = dt / 0.86
                self.currentLevel += (self.targetLevel - self.currentLevel) * min(1.0, releaseSpeed * 1.5)
            }

            self.needsDisplay = true
        }
        RunLoop.main.add(animationTimer!, forMode: .common)
    }

    public func stopAnimation() {
        animationTimer?.invalidate()
        animationTimer = nil
    }

    deinit {
        stopAnimation()
    }

    public override func viewDidChangeEffectiveAppearance() {
        super.viewDidChangeEffectiveAppearance()
        let isDark = effectiveAppearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
        if isDarkMode != isDark {
            isDarkMode = isDark
        }
    }

    // MARK: - Drawing
    public override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        guard let ctx = NSGraphicsContext.current?.cgContext else { return }

        let width = bounds.width
        let height = bounds.height
        guard width > 10 && height > 2 else { return }

        // Breathing idle presence: 5.2s sine wave
        let breathe = (sin(clockTime * (2.0 * .pi / 5.2)) + 1.0) / 2.0
        let effectiveIdle = idle * (0.8 + 0.2 * breathe)

        if isProcessing {
            drawProcessingBeam(ctx: ctx, width: width, height: height)
        } else {
            drawSoundReactiveGlow(ctx: ctx, width: width, height: height, idlePresence: effectiveIdle)
        }
    }

    // Sound-reactive mode: 7 lobes blooming from the bottom edge
    private func drawSoundReactiveGlow(ctx: CGContext, width: Double, height: Double, idlePresence: Double) {
        let activeLevel = max(idlePresence, currentLevel)
        let midX = width / 2.0
        let bottomY = 0.0 // bottom of view in AppKit default coords

        // Flow phase drift
        let flowShift = sin(clockTime * 0.8) * 12.0

        ctx.saveGState()

        // 1. Bloom halo behind everything
        for lobe in lobes {
            let lobeX = midX + (lobe.xOffsetRatio * (width * 0.42) * spread) + flowShift
            let lobeH = lobe.height * (1.0 + reach * activeLevel)
            let lobeW = lobe.width * (1.0 + 0.3 * activeLevel)
            let alpha = (0.25 + 0.65 * activeLevel) * (isDarkMode ? 0.75 : 0.55)

            let lobeRect = CGRect(x: lobeX - lobeW / 2.0, y: bottomY - lobeH * 0.25, width: lobeW, height: lobeH)
            drawRadialLobe(ctx: ctx, rect: lobeRect, color: lobe.color.withAlphaComponent(CGFloat(alpha)))
        }

        // 2. Crisp bottom stroke along the bottom edge
        let strokeY = 1.0
        let strokePath = CGMutablePath()
        strokePath.move(to: CGPoint(x: width * 0.1, y: strokeY))
        strokePath.addLine(to: CGPoint(x: width * 0.9, y: strokeY))

        ctx.setLineWidth(1.8)
        let strokeAlpha = min(1.0, 0.4 + 0.6 * activeLevel)
        ctx.setStrokeColor(NSColor.white.withAlphaComponent(CGFloat(strokeAlpha)).cgColor)
        ctx.addPath(strokePath)
        ctx.strokePath()

        // 3. Center epicenter white core
        let coreW = 60.0 * (1.0 + 0.4 * activeLevel)
        let coreH = 14.0 * (1.0 + reach * activeLevel)
        let coreRect = CGRect(x: midX - coreW / 2.0, y: bottomY - 2, width: coreW, height: coreH)
        let coreColor = isDarkMode ? NSColor.white.withAlphaComponent(CGFloat(0.35 + 0.55 * activeLevel))
                                   : NSColor.white.withAlphaComponent(CGFloat(0.5 + 0.5 * activeLevel))
        drawRadialLobe(ctx: ctx, rect: coreRect, color: coreColor)

        ctx.restoreGState()
    }

    // Processing mode: compact traveling beam sweeping side-to-side along the bottom edge
    private func drawProcessingBeam(ctx: CGContext, width: Double, height: Double) {
        let midX = width / 2.0
        let sweepPeriod = processingDuration * 2.0
        let sweepPhase = fmod(clockTime, sweepPeriod) / sweepPeriod
        // Cubic ease in-out sweep
        let rawSweep = sin(sweepPhase * 2.0 * .pi)
        let sweepEased = rawSweep * abs(rawSweep) // gives curved turnaround
        let travelRange = width * 0.38
        let beamX = midX + sweepEased * travelRange
        let bottomY = 0.0

        ctx.saveGState()

        // Soft lit base glow across entire width
        let baseRect = CGRect(x: width * 0.15, y: bottomY, width: width * 0.7, height: height * 0.7)
        drawRadialLobe(ctx: ctx, rect: baseRect, color: NSColor(red: 175/255, green: 70/255, blue: 255/255, alpha: 0.18))

        // Traveling beam colorful lobes
        let beamColors: [NSColor] = [
            NSColor(red: 255/255, green: 70/255, blue: 120/255, alpha: 0.8), // pink
            NSColor(red: 60/255, green: 190/255, blue: 255/255, alpha: 0.9),  // cyan
            NSColor(red: 175/255, green: 70/255, blue: 255/255, alpha: 0.85), // purple
            NSColor(red: 60/255, green: 220/255, blue: 130/255, alpha: 0.8)   // green
        ]

        for (idx, color) in beamColors.enumerated() {
            let offset = (Double(idx) - 1.5) * 14.0
            let lobeRect = CGRect(x: beamX + offset - 22, y: bottomY - 5, width: 44, height: height * 0.85)
            drawRadialLobe(ctx: ctx, rect: lobeRect, color: color)
        }

        // White hot epicenter of traveling beam
        let coreRect = CGRect(x: beamX - 20, y: bottomY - 2, width: 40, height: height * 0.5)
        drawRadialLobe(ctx: ctx, rect: coreRect, color: NSColor.white.withAlphaComponent(0.95))

        // Glowing bottom track line
        ctx.setLineWidth(2.0)
        ctx.setStrokeColor(NSColor.white.withAlphaComponent(0.85).cgColor)
        ctx.beginPath()
        ctx.move(to: CGPoint(x: beamX - 30, y: 1.0))
        ctx.addLine(to: CGPoint(x: beamX + 30, y: 1.0))
        ctx.strokePath()

        ctx.restoreGState()
    }

    private func drawRadialLobe(ctx: CGContext, rect: CGRect, color: NSColor) {
        ctx.saveGState()
        let colors = [color.cgColor, color.withAlphaComponent(0.0).cgColor] as CFArray
        let locations: [CGFloat] = [0.0, 1.0]
        guard let gradient = CGGradient(colorsSpace: CGColorSpaceCreateDeviceRGB(), colors: colors, locations: locations) else {
            ctx.restoreGState()
            return
        }

        let center = CGPoint(x: rect.midX, y: rect.minY + 2)
        let radius = max(rect.width, rect.height) / 2.0

        ctx.saveGState()
        // Scale Y to create an ellipse
        let scaleY = rect.height / rect.width
        ctx.translateBy(x: center.x, y: center.y)
        ctx.scaleBy(x: 1.0, y: scaleY)
        ctx.drawRadialGradient(gradient, startCenter: .zero, startRadius: 0.0, endCenter: .zero, endRadius: radius, options: .drawsAfterEndLocation)
        ctx.restoreGState()

        ctx.restoreGState()
    }
}
