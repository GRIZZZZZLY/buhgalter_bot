import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl text-sm font-medium transition-all duration-150 disabled:pointer-events-none disabled:opacity-50 active:scale-[0.97]',
  {
    variants: {
      variant: {
        default: 'bg-tg-button text-tg-button-text shadow-sm hover:opacity-90',
        destructive: 'bg-tg-destructive/10 text-tg-destructive hover:bg-tg-destructive/20',
        outline: 'border border-tg-hint/30 bg-transparent text-tg-text hover:bg-tg-secondary-bg',
        ghost: 'text-tg-text hover:bg-tg-secondary-bg',
        link: 'text-tg-link underline-offset-4 hover:underline',
      },
      size: {
        default: 'h-11 px-5 py-2',
        sm: 'h-9 px-3 text-xs',
        lg: 'h-13 px-8 text-base',
        icon: 'h-10 w-10',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  },
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button'
    return (
      <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />
    )
  },
)
Button.displayName = 'Button'

export { Button, buttonVariants }
