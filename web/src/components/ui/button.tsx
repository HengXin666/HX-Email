import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "../../lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-md border text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300 disabled:pointer-events-none disabled:opacity-45",
  {
    variants: {
      variant: {
        default:
          "border-emerald-400/55 bg-emerald-400/15 text-emerald-100 hover:bg-emerald-400/25",
      },
      size: {
        default: "h-10 px-4 py-2",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button
      className={cn(buttonVariants({ variant, size, className }))}
      ref={ref}
      {...props}
    />
  ),
);

Button.displayName = "Button";
