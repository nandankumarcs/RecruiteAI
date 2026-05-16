import { cn } from "@/lib/utils"

export type TextureType =
  | "dots"
  | "grid"
  | "noise"
  | "crosshatch"
  | "diagonal"
  | "scatteredDots"
  | "halftone"
  | "triangular"
  | "chevron"
  | "paperGrain"
  | "horizontalLines"
  | "verticalLines"
  | "none"

interface TextureOverlayProps {
  texture: TextureType
  opacity?: number
  className?: string
}

const texturePatterns: Record<TextureType, string> = {
  dots: "bg-[radial-gradient(circle_at_1px_1px,currentColor_1px,transparent_0)] bg-[length:8px_8px]",
  grid: "bg-[linear-gradient(currentColor_1px,transparent_1px),linear-gradient(90deg,currentColor_1px,transparent_1px)] bg-[length:12px_12px]",
  noise:
    "bg-[radial-gradient(circle_at_2px_2px,currentColor_1px,transparent_0)] bg-[length:6px_6px]",
  crosshatch:
    "bg-[repeating-linear-gradient(45deg,transparent,transparent_2px,currentColor_2px,currentColor_4px),repeating-linear-gradient(-45deg,transparent,transparent_2px,currentColor_2px,currentColor_4px)]",
  diagonal:
    "bg-[repeating-linear-gradient(-45deg,currentColor,currentColor_1px,transparent_1px,transparent_6px)]",
  scatteredDots:
    "bg-[radial-gradient(circle_at_3px_7px,currentColor_1px,transparent_0),radial-gradient(circle_at_11px_2px,currentColor_1px,transparent_0),radial-gradient(circle_at_7px_12px,currentColor_1px,transparent_0)] bg-[length:16px_16px]",
  halftone:
    "bg-[radial-gradient(circle,currentColor_25%,transparent_25%)] bg-[length:10px_10px] bg-[position:0_0,5px_5px]",
  triangular:
    "bg-[conic-gradient(from_0deg_at_50%_50%,currentColor_0deg_120deg,transparent_120deg_240deg,currentColor_240deg_360deg)] bg-[length:8px_8px] bg-[position:0_0,4px_4px]",
  chevron:
    "bg-[repeating-linear-gradient(45deg,currentColor_0px,currentColor_2px,transparent_2px,transparent_8px),repeating-linear-gradient(-45deg,currentColor_0px,currentColor_2px,transparent_2px,transparent_8px)]",
  paperGrain:
    "bg-[repeating-linear-gradient(0deg,currentColor_0px,transparent_1px,transparent_3px),repeating-linear-gradient(90deg,currentColor_0px,transparent_1px,transparent_4px),repeating-linear-gradient(45deg,currentColor_0px,transparent_1px,transparent_5px)]",
  horizontalLines:
    "bg-[repeating-linear-gradient(0deg,currentColor_0px,currentColor_1px,transparent_1px,transparent_4px)]",
  verticalLines:
    "bg-[repeating-linear-gradient(90deg,currentColor_0px,currentColor_1px,transparent_1px,transparent_4px)]",
  none: "",
}

const defaultOpacities: Record<TextureType, number> = {
  dots: 1,
  grid: 1,
  noise: 1,
  crosshatch: 1,
  diagonal: 1,

  scatteredDots: 1,
  halftone: 1,
  triangular: 1,
  chevron: 1,
  paperGrain: 1,
  horizontalLines: 1,
  verticalLines: 1,
  none: 0,
}

export function TextureOverlay({
  texture,
  opacity,
  className,
}: TextureOverlayProps) {
  if (texture === "none") return null

  const finalOpacity = opacity ?? defaultOpacities[texture]
  const pattern = texturePatterns[texture]

  return (
    <div
      className={cn("absolute inset-0 pointer-events-none", pattern, className)}
      style={{ opacity: finalOpacity }}
    />
  )
}
