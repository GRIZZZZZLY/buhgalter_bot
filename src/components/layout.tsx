import { useEffect } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router'
import { AnimatePresence, motion } from 'motion/react'
import { backButton } from '@/lib/telegram'

const pageVariants = {
  initial: { opacity: 0, x: 20 },
  animate: { opacity: 1, x: 0 },
  exit: { opacity: 0, x: -20 },
}

const pageTransition = {
  type: 'tween' as const,
  duration: 0.2,
  ease: 'easeInOut',
}

export function Layout() {
  const navigate = useNavigate()
  const location = useLocation()
  const isRoot = location.pathname === '/'

  // Sync Telegram Back Button with router
  useEffect(() => {
    try {
      if (isRoot) {
        backButton.hide()
      } else {
        backButton.show()
      }
      const cleanup = backButton.onClick(() => void navigate(-1))
      return cleanup
    } catch {
      // Outside Telegram
    }
  }, [isRoot, navigate])

  return (
    <div className="min-h-screen bg-tg-secondary-bg">
      <AnimatePresence mode="wait">
        <motion.div
          key={location.pathname}
          variants={pageVariants}
          initial="initial"
          animate="animate"
          exit="exit"
          transition={pageTransition}
        >
          <Outlet />
        </motion.div>
      </AnimatePresence>
    </div>
  )
}
