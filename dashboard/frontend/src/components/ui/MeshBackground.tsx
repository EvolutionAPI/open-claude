import { useEffect, useRef } from 'react'

interface MeshBackgroundProps {
  density?: number
  maxParticles?: number
  maxDistance?: number
  particleColor?: string
  lineColor?: string
  className?: string
  zIndex?: number
}

export function MeshBackground({
  density = 18000,
  maxParticles = 80,
  maxDistance = 150,
  particleColor = 'rgba(0, 255, 167, 0.25)',
  lineColor = '0, 255, 167',
  className = 'fixed inset-0 pointer-events-none',
  zIndex = 0,
}: MeshBackgroundProps) {
  const ref = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduced) return

    const canvas = ref.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let animId = 0
    let particles: { x: number; y: number; vx: number; vy: number }[] = []

    const resize = () => {
      canvas.width = window.innerWidth
      canvas.height = window.innerHeight
    }

    const init = () => {
      resize()
      const count = Math.floor((canvas.width * canvas.height) / density)
      particles = Array.from({ length: Math.min(count, maxParticles) }, () => ({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        vx: (Math.random() - 0.5) * 0.3,
        vy: (Math.random() - 0.5) * 0.3,
      }))
    }

    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height)

      for (let i = 0; i < particles.length; i++) {
        const p = particles[i]
        p.x += p.vx
        p.y += p.vy
        if (p.x < 0 || p.x > canvas.width) p.vx *= -1
        if (p.y < 0 || p.y > canvas.height) p.vy *= -1

        ctx.beginPath()
        ctx.arc(p.x, p.y, 1.5, 0, Math.PI * 2)
        ctx.fillStyle = particleColor
        ctx.fill()

        for (let j = i + 1; j < particles.length; j++) {
          const q = particles[j]
          const dx = p.x - q.x
          const dy = p.y - q.y
          const dist = Math.sqrt(dx * dx + dy * dy)
          if (dist < maxDistance) {
            ctx.beginPath()
            ctx.moveTo(p.x, p.y)
            ctx.lineTo(q.x, q.y)
            ctx.strokeStyle = `rgba(${lineColor}, ${0.06 * (1 - dist / maxDistance)})`
            ctx.lineWidth = 0.5
            ctx.stroke()
          }
        }
      }
      animId = requestAnimationFrame(draw)
    }

    init()
    draw()
    window.addEventListener('resize', init)
    return () => {
      cancelAnimationFrame(animId)
      window.removeEventListener('resize', init)
    }
  }, [density, maxParticles, maxDistance, particleColor, lineColor])

  return <canvas ref={ref} aria-hidden className={className} style={{ zIndex }} />
}
