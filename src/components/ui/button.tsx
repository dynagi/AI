import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

// Classic beveled Windows button: raised by default, inset while pressed (handled by .retro-bevel in globals.css).
const buttonVariants = cva(
  "inline-flex select-none items-center justify-center gap-2 whitespace-nowrap font-mono text-[13px] font-semibold text-black disabled:pointer-events-none disabled:opacity-60",
  {
    variants: {
      variant: {
        default: "retro-bevel",
        secondary: "retro-bevel",
        outline: "retro-bevel bg-white",
        yellow: "retro-bevel bg-cream hover:bg-[#fff7b8]",
        ghost: "border-2 border-transparent bg-transparent hover:border-black hover:bg-white/70",
        destructive: "retro-bevel bg-[#FF3333] text-white hover:bg-[#ff5555]",
      },
      size: { default: "h-9 px-4", sm: "h-7 px-2.5 text-xs", lg: "h-11 px-6 text-sm" },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(({ className, variant, size, asChild = false, ...props }, ref) => {
  const Comp = asChild ? Slot : "button";
  return <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />;
});
Button.displayName = "Button";

export { Button, buttonVariants };
