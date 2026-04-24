interface SpinnerProps {
  size?: number
  className?: string
}

export function Spinner({ size = 20, className = '' }: SpinnerProps) {
  return (
    <span
      role="status"
      aria-label="Loading"
      className={`inline-block border-2 border-[#00FFA7]/20 border-t-[#00FFA7] rounded-full animate-spin ${className}`}
      style={{ width: size, height: size }}
    />
  )
}
