import type React from "react"

import { cn } from "@/lib/utils"

export type TextureVariant =
  | "fabric-of-squares"
  | "grid-noise"
  | "inflicted"
  | "debut-light"
  | "groovepaper"
  | "none"

interface BackgroundImageTextureProps {
  variant?: TextureVariant
  opacity?: number
  className?: string
  children?: React.ReactNode
}

const texturePatterns: Record<Exclude<TextureVariant, "none">, string> = {
  "fabric-of-squares":
    "bg-[radial-gradient(circle,currentColor_1px,transparent_1px)] bg-[length:16px_16px]",
  "grid-noise":
    "bg-[linear-gradient(currentColor_1px,transparent_1px),linear-gradient(90deg,currentColor_1px,transparent_1px)] bg-[length:24px_24px]",
  inflicted:
    "bg-[radial-gradient(circle_at_50%_50%,currentColor_0%,transparent_50%)] bg-[length:32px_32px]",
  "debut-light":
    "bg-[radial-gradient(circle,transparent_70%,currentColor_100%)] bg-[length:20px_20px]",
  groovepaper:
    "bg-[repeating-linear-gradient(0deg,transparent,transparent_2px,currentColor_2px,currentColor_4px),repeating-linear-gradient(90deg,transparent,transparent_2px,currentColor_2px,currentColor_4px)]",
}

export function BackgroundImageTexture({
  variant = "fabric-of-squares",
  opacity = 0.5,
  className,
  children,
}: BackgroundImageTextureProps) {
  if (variant === "none") return <>{children}</>

  const pattern = texturePatterns[variant]

  return (
    <div className={cn("relative", className)}>
      <div
        aria-hidden="true"
        className={cn("pointer-events-none absolute inset-0", pattern)}
        style={{ opacity }}
      />
      {children && <div className="relative">{children}</div>}
    </div>
  )
}
