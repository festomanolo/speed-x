import AppKit

class SpectrometerWaveView: NSView {
    var isDarkMode: Bool = true
    private var displayTimer: Timer?

    private var phase: CGFloat = 0.0
    private var targetLevel: CGFloat = 0.0
    private var smoothLevel: CGFloat = 0.0

    // Gemini Live Signature Colors
    private let colorCyan = NSColor(calibratedRed: 0/255, green: 229/255, blue: 255/255, alpha: 0.85)
    private let colorPurple = NSColor(calibratedRed: 157/255, green: 78/255, blue: 221/255, alpha: 0.85)
    private let colorPink = NSColor(calibratedRed: 255/255, green: 64/255, blue: 129/255, alpha: 0.80)
    private let colorCore = NSColor(calibratedWhite: 1.0, alpha: 0.95)

    override var isFlipped: Bool { true }

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true
        layer?.cornerRadius = 13
        layer?.masksToBounds = true
    }

    required init?(coder: NSCoder) {
        super.init(coder: coder)
        wantsLayer = true
        layer?.cornerRadius = 13
        layer?.masksToBounds = true
    }

    deinit {
        stopAnimating()
    }

    func setAudioLevel(_ level: Float) {
        self.targetLevel = CGFloat(level)
    }

    func startAnimating() {
        stopAnimating()
        displayTimer = Timer.scheduledTimer(withTimeInterval: 1.0 / 60.0, repeats: true) { [weak self] _ in
            self?.updateFrame()
        }
    }

    func stopAnimating() {
        displayTimer?.invalidate()
        displayTimer = nil
        targetLevel = 0.0
        smoothLevel = 0.0
        needsDisplay = true
    }

    private func updateFrame() {
        // Smooth easing towards target audio level
        let smoothingFactor: CGFloat = (targetLevel > smoothLevel) ? 0.35 : 0.12
        smoothLevel += (targetLevel - smoothLevel) * smoothingFactor

        // Flowing phase speed increases with voice input
        let speed: CGFloat = 0.07 + (smoothLevel * 0.14)
        phase += speed

        needsDisplay = true
    }

    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        guard let ctx = NSGraphicsContext.current?.cgContext else { return }

        let w = bounds.width
        let h = bounds.height
        let midY = h / 2.0

        ctx.saveGState()

        // 1. Frosted Liquid Glass Container
        let containerRect = bounds.insetBy(dx: 1, dy: 1)
        let containerPath = NSBezierPath(roundedRect: containerRect, xRadius: 12, yRadius: 12)
        let bgAlpha: CGFloat = isDarkMode ? 0.15 : 0.40
        let bgColor = isDarkMode ? NSColor(calibratedWhite: 1.0, alpha: bgAlpha) : NSColor(calibratedWhite: 1.0, alpha: bgAlpha)
        bgColor.setFill()
        containerPath.fill()

        let strokeColor = isDarkMode ? NSColor(white: 1.0, alpha: 0.25) : NSColor(white: 1.0, alpha: 0.65)
        strokeColor.setStroke()
        containerPath.lineWidth = 1.0
        containerPath.stroke()

        // Clip drawing inside container
        containerPath.addClip()

        // 2. Draw Gemini Live Undulating Multi-Wave Ribbon
        let baseAmp: CGFloat = 3.5
        let maxAmp = (h / 2.0) - 6.0
        let amp = baseAmp + (maxAmp - baseAmp) * smoothLevel

        // Layer 1: Electric Cyan Wave
        drawSineWave(
            ctx: ctx,
            width: w,
            midY: midY,
            amplitude: amp * 0.95,
            frequency: 0.024,
            phaseOffset: phase,
            color: colorCyan,
            lineWidth: 2.2,
            glow: true
        )

        // Layer 2: Electric Purple / Violet Wave (offset harmonic)
        drawSineWave(
            ctx: ctx,
            width: w,
            midY: midY,
            amplitude: amp * 0.85,
            frequency: 0.032,
            phaseOffset: -phase * 0.85 + 1.2,
            color: colorPurple,
            lineWidth: 2.0,
            glow: true
        )

        // Layer 3: Vibrant Coral Pink Wave
        drawSineWave(
            ctx: ctx,
            width: w,
            midY: midY,
            amplitude: amp * 0.70,
            frequency: 0.018,
            phaseOffset: phase * 1.25 + 2.4,
            color: colorPink,
            lineWidth: 1.8,
            glow: false
        )

        // Layer 4: Crisp White Glow Core
        drawSineWave(
            ctx: ctx,
            width: w,
            midY: midY,
            amplitude: amp * 0.60,
            frequency: 0.026,
            phaseOffset: phase + 0.4,
            color: colorCore,
            lineWidth: 1.2,
            glow: false
        )

        // 3. Central Reactive Spectrometer Equalizer Bars
        drawSpectrometerBars(ctx: ctx, centerX: w / 2.0, centerY: midY, maxHeight: h - 14)

        ctx.restoreGState()
    }

    private func drawSineWave(
        ctx: CGContext,
        width: CGFloat,
        midY: CGFloat,
        amplitude: CGFloat,
        frequency: CGFloat,
        phaseOffset: CGFloat,
        color: NSColor,
        lineWidth: CGFloat,
        glow: Bool
    ) {
        ctx.saveGState()

        if glow {
            ctx.setShadow(offset: .zero, blur: 6 + smoothLevel * 8, color: color.withAlphaComponent(0.6).cgColor)
        }

        ctx.setStrokeColor(color.cgColor)
        ctx.setLineWidth(lineWidth)
        ctx.setLineCap(.round)
        ctx.setLineJoin(.round)

        ctx.beginPath()
        let step: CGFloat = 2.0
        var isFirst = true

        for x in stride(from: CGFloat(0), through: width, by: step) {
            // Edge taper envelope (soft fade out at left and right edges)
            let normalizedX = x / width
            let envelope = sin(normalizedX * .pi)

            let y = midY + sin(x * frequency + phaseOffset) * amplitude * envelope

            if isFirst {
                ctx.move(to: CGPoint(x: x, y: y))
                isFirst = false
            } else {
                ctx.addLine(to: CGPoint(x: x, y: y))
            }
        }

        ctx.strokePath()
        ctx.restoreGState()
    }

    private func drawSpectrometerBars(ctx: CGContext, centerX: CGFloat, centerY: CGFloat, maxHeight: CGFloat) {
        let barCount = 7
        let barWidth: CGFloat = 3.6
        let barSpacing: CGFloat = 6.2
        let totalWidth = CGFloat(barCount) * barWidth + CGFloat(barCount - 1) * barSpacing
        var startX = centerX - totalWidth / 2.0

        let harmonicWeights: [CGFloat] = [0.65, 0.85, 1.05, 1.25, 1.05, 0.85, 0.65]
        let barColors: [NSColor] = [
            colorCyan,
            NSColor(calibratedRed: 33/255, green: 150/255, blue: 243/255, alpha: 0.9),
            colorPurple,
            colorCore,
            colorPink,
            NSColor(calibratedRed: 255/255, green: 110/255, blue: 64/255, alpha: 0.9),
            colorCyan
        ]

        let minBarHeight: CGFloat = 5.0

        for i in 0..<barCount {
            let weight = harmonicWeights[i]
            // Add subtle animated breathing wobble even when idle
            let idleWobble = sin(phase * 2.0 + CGFloat(i) * 0.9) * 2.5
            let activeHeight = smoothLevel * (maxHeight - minBarHeight) * weight
            let h = max(minBarHeight, min(maxHeight, minBarHeight + activeHeight + idleWobble))

            let barRect = NSRect(x: startX, y: centerY - h / 2.0, width: barWidth, height: h)
            let path = NSBezierPath(roundedRect: barRect, xRadius: barWidth / 2.0, yRadius: barWidth / 2.0)

            ctx.saveGState()
            if smoothLevel > 0.15 {
                ctx.setShadow(offset: .zero, blur: 5 + smoothLevel * 6, color: barColors[i].cgColor)
            }
            barColors[i].setFill()
            path.fill()
            ctx.restoreGState()

            startX += barWidth + barSpacing
        }
    }
}
