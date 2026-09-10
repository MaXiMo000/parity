import { useEffect, useRef } from 'react'

/** Focus/inert/Escape handling for a slide-in panel — native `inert`
 * instead of a hand-rolled focus trap, focus returned on close. */
export function useModalPanel(active: boolean, onClose: () => void) {
  const closeRef = useRef<HTMLButtonElement>(null)
  const returnFocusTo = useRef<Element | null>(null)

  useEffect(() => {
    if (!active) return
    returnFocusTo.current = document.activeElement
    closeRef.current?.focus()

    const root = document.querySelector('.scene-root')
    root?.setAttribute('inert', '')

    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      root?.removeAttribute('inert')
      ;(returnFocusTo.current as HTMLElement | null)?.focus?.()
    }
  }, [active, onClose])

  return closeRef
}
