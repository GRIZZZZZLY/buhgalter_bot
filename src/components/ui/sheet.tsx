import * as React from 'react'
import { cn } from '@/lib/utils'
import { motion, AnimatePresence } from 'motion/react'

interface SheetProps {
  open: boolean
  onClose: () => void
  children: React.ReactNode
  className?: string
}

export function Sheet({ open, onClose, children, className }: SheetProps) {
  // Close on Escape
  React.useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, onClose])

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop */}
          <motion.div
            key="backdrop"
            className="fixed inset-0 z-40 bg-black/40"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={onClose}
          />
          {/* Sheet */}
          <motion.div
            key="sheet"
            className={cn(
              'fixed bottom-0 left-0 right-0 z-50 mx-auto max-w-lg',
              'rounded-t-3xl bg-tg-section-bg shadow-2xl',
              'safe-bottom',
              className,
            )}
            initial={{ y: '100%' }}
            animate={{ y: 0 }}
            exit={{ y: '100%' }}
            transition={{ type: 'spring', damping: 30, stiffness: 300 }}
            drag="y"
            dragConstraints={{ top: 0 }}
            dragElastic={{ top: 0, bottom: 0.3 }}
            onDragEnd={(_event, info) => {
              if (info.offset.y > 80) onClose()
            }}
          >
            {/* Grabber */}
            <div className="mx-auto mt-3 mb-1 h-1 w-10 rounded-full bg-tg-hint/30" />
            {children}
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}
