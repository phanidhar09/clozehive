import { useEffect, useRef } from 'react'

/**
 * Tracks cursor position relative to a container and smoothly updates a
 * floating glow orb via requestAnimationFrame lerp — zero React re-renders.
 *
 * Usage:
 *   const { containerRef, glowRef } = useCursorGlow()
 *   <div ref={containerRef}>
 *     <div ref={glowRef} style={{ opacity: 0, position: 'absolute', pointerEvents: 'none' }} />
 *     …content…
 *   </div>
 */
export function useCursorGlow(options?: { lerpFactor?: number; orbitRadius?: number }) {
  const { lerpFactor = 0.07, orbitRadius = 250 } = options ?? {}

  const containerRef = useRef<HTMLDivElement>(null)
  const glowRef      = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const container = containerRef.current
    const glow      = glowRef.current
    if (!container || !glow) return

    let raf: number
    let active      = false
    let targetX     = 0
    let targetY     = 0
    let currentX    = 0
    let currentY    = 0

    const tick = () => {
      if (!active) return
      currentX += (targetX - currentX) * lerpFactor
      currentY += (targetY - currentY) * lerpFactor
      glow.style.transform = `translate3d(${currentX}px,${currentY}px,0)`
      raf = requestAnimationFrame(tick)
    }

    const onMove = (e: MouseEvent) => {
      const { left, top } = container.getBoundingClientRect()
      targetX = e.clientX - left - orbitRadius
      targetY = e.clientY - top  - orbitRadius
    }

    const onEnter = () => {
      active = true
      glow.style.opacity = '1'
      raf = requestAnimationFrame(tick)
    }

    const onLeave = () => {
      active = false
      glow.style.opacity = '0'
      cancelAnimationFrame(raf)
    }

    container.addEventListener('mousemove', onMove, { passive: true })
    container.addEventListener('mouseenter', onEnter)
    container.addEventListener('mouseleave', onLeave)

    return () => {
      container.removeEventListener('mousemove', onMove)
      container.removeEventListener('mouseenter', onEnter)
      container.removeEventListener('mouseleave', onLeave)
      cancelAnimationFrame(raf)
    }
  }, [lerpFactor, orbitRadius])

  return { containerRef, glowRef }
}
