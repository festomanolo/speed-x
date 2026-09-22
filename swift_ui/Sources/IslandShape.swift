import AppKit

class IslandShape {
    static func createPath(in rect: NSRect, width: CGFloat = 72, topFillet: CGFloat = 40, bottomFillet: CGFloat = 40) -> NSBezierPath {
        let path = NSBezierPath()
        let right = rect.maxX
        let top = rect.minY
        let bottom = rect.maxY
        let left = right - width

        // Start at top-right on the screen bezel
        path.move(to: NSPoint(x: right, y: top))

        // Top concave curve: sweeps from bezel (right) inwards to the vertical edge (left)
        path.curve(
            to: NSPoint(x: left, y: top + topFillet),
            controlPoint1: NSPoint(x: right - 8, y: top + 4),
            controlPoint2: NSPoint(x: left, y: top + topFillet * 0.4)
        )

        // Vertical straight edge
        path.line(to: NSPoint(x: left, y: bottom - bottomFillet))

        // Bottom concave curve: sweeps back from vertical edge (left) outwards to the bezel (right)
        path.curve(
            to: NSPoint(x: right, y: bottom),
            controlPoint1: NSPoint(x: left, y: bottom - bottomFillet * 0.4),
            controlPoint2: NSPoint(x: right - 8, y: bottom - 4)
        )

        // Close along the screen bezel
        path.line(to: NSPoint(x: right, y: top))
        path.close()

        return path
    }

    static func createPopoverPath(in rect: NSRect, arrowY: CGFloat, arrowWidth: CGFloat = 12, arrowHeight: CGFloat = 14, cornerRadius: CGFloat = 18) -> NSBezierPath {
        let path = NSBezierPath()
        let bodyRect = NSRect(x: rect.minX, y: rect.minY, width: rect.width - arrowWidth, height: rect.height)
        let minX = bodyRect.minX
        let maxX = bodyRect.maxX
        let minY = bodyRect.minY
        let maxY = bodyRect.maxY

        // Start top-left
        path.move(to: NSPoint(x: minX + cornerRadius, y: minY))

        // Top edge & top-right corner
        path.line(to: NSPoint(x: maxX - cornerRadius, y: minY))
        path.curve(to: NSPoint(x: maxX, y: minY + cornerRadius),
                   controlPoint1: NSPoint(x: maxX, y: minY),
                   controlPoint2: NSPoint(x: maxX, y: minY + cornerRadius))

        // Right edge down to arrow
        let clampedArrowY = max(minY + cornerRadius + arrowHeight, min(maxY - cornerRadius - arrowHeight, arrowY))
        let arrowTopY = clampedArrowY - arrowHeight / 2
        let arrowBottomY = clampedArrowY + arrowHeight / 2

        path.line(to: NSPoint(x: maxX, y: arrowTopY))
        // Pointing arrow beak pointing directly to the gauge
        path.line(to: NSPoint(x: maxX + arrowWidth, y: clampedArrowY))
        path.line(to: NSPoint(x: maxX, y: arrowBottomY))

        // Right edge down to bottom-right corner
        path.line(to: NSPoint(x: maxX, y: maxY - cornerRadius))
        path.curve(to: NSPoint(x: maxX - cornerRadius, y: maxY),
                   controlPoint1: NSPoint(x: maxX, y: maxY),
                   controlPoint2: NSPoint(x: maxX, y: maxY - cornerRadius))

        // Bottom edge & bottom-left corner
        path.line(to: NSPoint(x: minX + cornerRadius, y: maxY))
        path.curve(to: NSPoint(x: minX, y: maxY - cornerRadius),
                   controlPoint1: NSPoint(x: minX, y: maxY),
                   controlPoint2: NSPoint(x: minX, y: maxY - cornerRadius))

        // Left edge & top-left corner
        path.line(to: NSPoint(x: minX, y: minY + cornerRadius))
        path.curve(to: NSPoint(x: minX + cornerRadius, y: minY),
                   controlPoint1: NSPoint(x: minX, y: minY),
                   controlPoint2: NSPoint(x: minX + cornerRadius, y: minY))

        path.close()
        return path
    }
}
