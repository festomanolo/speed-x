import SwiftUI

/// The side notch: a slab attached to the right screen bezel whose top and bottom flare
/// into the bezel with concave fillets, then turn into the body with convex corners.
///
///   bezel ──╮
///            ╰──╮          flare (concave), tangent to the bezel at the start
///               │          convex corner of radius `cornerRadius`
///               │  body
///            ╭──╯
///   bezel ──╯
struct SideNotchShape: Shape {
    var flare: CGFloat = 40          // vertical extent of each concave fillet
    var cornerRadius: CGFloat = 34   // convex corner where the flare meets the body

    func path(in rect: CGRect) -> Path {
        let w = rect.width, h = rect.height
        let r = min(cornerRadius, w - 6)
        let f = min(flare, h / 4)
        var p = Path()
        p.move(to: CGPoint(x: w, y: 0))
        // Top flare: leaves the bezel vertically, arrives horizontally at the corner.
        p.addCurve(to: CGPoint(x: r, y: f),
                   control1: CGPoint(x: w, y: f * 0.62),
                   control2: CGPoint(x: r + (w - r) * 0.42, y: f))
        p.addArc(tangent1End: CGPoint(x: 0, y: f), tangent2End: CGPoint(x: 0, y: f + r), radius: r)
        p.addLine(to: CGPoint(x: 0, y: h - f - r))
        p.addArc(tangent1End: CGPoint(x: 0, y: h - f), tangent2End: CGPoint(x: r, y: h - f), radius: r)
        // Bottom flare back into the bezel.
        p.addCurve(to: CGPoint(x: w, y: h),
                   control1: CGPoint(x: r + (w - r) * 0.42, y: h - f),
                   control2: CGPoint(x: w, y: h - f * 0.62))
        p.closeSubpath()
        return p.offsetBy(dx: rect.minX, dy: rect.minY)
    }
}

/// Rounded card with a pointer on its right edge whose sides flare smoothly into the card.
struct PointerCardShape: Shape {
    var pointerY: CGFloat            // pointer tip, measured from the top of the card
    var pointerLength: CGFloat = 26
    var pointerHalfHeight: CGFloat = 24
    var cornerRadius: CGFloat = 26

    var animatableData: CGFloat {
        get { pointerY }
        set { pointerY = newValue }
    }

    func path(in rect: CGRect) -> Path {
        let body = CGRect(x: rect.minX, y: rect.minY, width: rect.width - pointerLength, height: rect.height)
        let r = min(cornerRadius, body.height / 2)
        let half = min(pointerHalfHeight, (body.height - 2 * r) / 2 - 10)
        let tipY = min(max(rect.minY + pointerY, body.minY + r + half), body.maxY - r - half)
        let tip = CGPoint(x: rect.maxX, y: tipY)

        var p = Path()
        p.move(to: CGPoint(x: body.minX + r, y: body.minY))
        p.addLine(to: CGPoint(x: body.maxX - r, y: body.minY))
        p.addArc(tangent1End: CGPoint(x: body.maxX, y: body.minY), tangent2End: CGPoint(x: body.maxX, y: body.minY + r), radius: r)
        if half > 4 {
            // Straight-sided beak (like the reference) with a soft fillet where it leaves
            // the card and a rounded tip.
            let fillet: CGFloat = 9
            let tipRound: CGFloat = 4
            let dx = tip.x - body.maxX, dy = half
            let len = (dx * dx + dy * dy).squareRoot()
            let ux = dx / len, uy = dy / len                     // unit vector base -> tip (upper side)
            let upperBase = CGPoint(x: body.maxX, y: tipY - half)
            let lowerBase = CGPoint(x: body.maxX, y: tipY + half)
            p.addLine(to: CGPoint(x: body.maxX, y: upperBase.y - fillet))
            p.addQuadCurve(to: CGPoint(x: upperBase.x + ux * fillet, y: upperBase.y + uy * fillet), control: upperBase)
            p.addLine(to: CGPoint(x: tip.x - ux * tipRound, y: tip.y - uy * tipRound))
            p.addQuadCurve(to: CGPoint(x: tip.x - ux * tipRound, y: tip.y + uy * tipRound), control: tip)
            p.addLine(to: CGPoint(x: lowerBase.x + ux * fillet, y: lowerBase.y - uy * fillet))
            p.addQuadCurve(to: CGPoint(x: body.maxX, y: lowerBase.y + fillet), control: lowerBase)
        }
        p.addLine(to: CGPoint(x: body.maxX, y: body.maxY - r))
        p.addArc(tangent1End: CGPoint(x: body.maxX, y: body.maxY), tangent2End: CGPoint(x: body.maxX - r, y: body.maxY), radius: r)
        p.addLine(to: CGPoint(x: body.minX + r, y: body.maxY))
        p.addArc(tangent1End: CGPoint(x: body.minX, y: body.maxY), tangent2End: CGPoint(x: body.minX, y: body.maxY - r), radius: r)
        p.addLine(to: CGPoint(x: body.minX, y: body.minY + r))
        p.addArc(tangent1End: CGPoint(x: body.minX, y: body.minY), tangent2End: CGPoint(x: body.minX + r, y: body.minY), radius: r)
        p.closeSubpath()
        return p
    }
}
