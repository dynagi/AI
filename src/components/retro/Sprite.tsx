import { cn } from "@/lib/utils";

/** Pixel-art sprite drawn from a character grid; each char maps to a palette colour, "." is transparent. */
export function Sprite({ rows, palette, px = 4, className }: { rows: string[]; palette: Record<string, string>; px?: number; className?: string }) {
  const h = rows.length;
  const w = Math.max(...rows.map((r) => r.length));
  const cells: JSX.Element[] = [];
  rows.forEach((row, y) =>
    [...row].forEach((ch, x) => {
      if (ch !== "." && palette[ch]) cells.push(<rect key={`${x}-${y}`} x={x} y={y} width={1.02} height={1.02} fill={palette[ch]} />);
    }),
  );
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width={w * px} height={h * px} shapeRendering="crispEdges" className={cn("pixel-art shrink-0", className)} aria-hidden>
      {cells}
    </svg>
  );
}

const K = "#000000", W = "#ffffff", P = "#9B72E8", L = "#D9C9F7", G = "#16A34A", Y = "#FFE04D", O = "#E0A800", R = "#FF3333", S = "#9a9a9a", M = "#7FE3B5";

export const Cash = () => (
  <Sprite px={4} palette={{ k: K, g: G, m: M, w: W }} rows={[
    "..kkkkkkkkkk..",
    ".kmmmmmmmmmmk.",
    ".kmkgggggkmmk.",
    ".kmkgkkkgkmmk.",
    ".kmmkgggkmmmk.",
    ".kmkgkkkgkmmk.",
    ".kmkgggggkmmk.",
    ".kmmmmmmmmmmk.",
    "..kkkkkkkkkk..",
  ]} />
);
export const Coins = () => (
  <Sprite px={4} palette={{ k: K, y: Y, o: O }} rows={[
    "..kkkkkk....",
    ".kyyyyyyk...",
    ".kyooooyk...",
    "kkkkkkkkkk..",
    "kyyyyyyyyk..",
    "kyooooooyk..",
    "kkkkkkkkkkkk",
    "kyyyyyyyyyyk",
    "kyooooooooyk",
    ".kkkkkkkkkk.",
  ]} />
);
export const Doc = () => (
  <Sprite px={4} palette={{ k: K, w: W, s: S }} rows={[
    ".kkkkkkk..",
    ".kwwwwwkk.",
    ".kwwwwwkwk",
    ".kwkkkwkkk",
    ".kwwwwwwwk",
    ".kwkkkkkwk",
    ".kwwwwwwwk",
    ".kwkkkkkwk",
    ".kwwwwwwwk",
    ".kkkkkkkkk",
  ]} />
);
export const Piggy = () => (
  <Sprite px={4} palette={{ k: K, p: P, l: L, w: W, y: Y }} rows={[
    "...kk........",
    "..kppk.kkkk..",
    ".kpppkkppppk.",
    "kppppppppppkk",
    "kpwkpppppppk.",
    "kpkkpppppplk.",
    "kppppppppppk.",
    ".kppppppppk..",
    "..kpk..kpk...",
    "..kkk..kkk...",
  ]} />
);
export const Siren = () => (
  <Sprite px={4} palette={{ k: K, r: R, w: W, s: S, y: Y }} rows={[
    "....kkkk....",
    "...krrwrk...",
    "..krrwrrrk..",
    "..krrwrrrk..",
    "..krrrrrrk..",
    ".kkkkkkkkkk.",
    ".ksssssssssk",
    ".kkkkkkkkkk.",
  ]} />
);
export const Robot = () => (
  <Sprite px={5} palette={{ k: K, p: P, l: L, g: "#33ff99", w: W, s: S }} rows={[
    ".......k.......",
    ".......k.......",
    "..kkkkkkkkkkk..",
    ".kppppppppppppk",
    ".kpkkkkkkkkkpk.",
    ".kpkgkkkkkgkpk.",
    ".kpkkkkkkkkkpk.",
    ".kppppkkkpppk..",
    "..kkkkkkkkkkk..",
    "...kllllllllk..",
    "..kpllllllllpk.",
    "..kkkkkkkkkkk..",
  ]} />
);
export const Plant = () => (
  <Sprite px={5} palette={{ k: K, g: G, m: M, p: P, l: L }} rows={[
    "...kk..kk....",
    "..kggkkggk...",
    ".kgggggggk...",
    "kggkgggkggk..",
    ".kkkkggkkk...",
    "....kgk......",
    "..kkkkkkkk...",
    "..kppppppk...",
    "..kpllllpk...",
    "...kppppk....",
    "....kkkk.....",
  ]} />
);
export const Smile = () => (
  <Sprite px={4} palette={{ k: K, y: Y }} rows={[
    "..kkkkkk..",
    ".kyyyyyyk.",
    "kyykyykyyk",
    "kyykyykyyk",
    "kyyyyyyyyk",
    "kykyyyykyk",
    "kyykkkkyyk",
    ".kyyyyyyk.",
    "..kkkkkk..",
  ]} />
);
