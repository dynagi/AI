import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva("inline-flex items-center border-2 border-black px-1.5 text-[11px] font-bold uppercase leading-5 text-black", {
  variants: {
    variant: {
      default: "bg-lavender",
      positive: "bg-mint-accent",
      negative: "bg-[#FF3333] text-white",
      warning: "bg-cream",
      outline: "bg-white",
    },
  },
  defaultVariants: { variant: "default" },
});

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}
