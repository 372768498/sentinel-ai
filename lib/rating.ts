export type RatingLabel = "STRONG" | "SOLID" | "NEUTRAL" | "CAUTION" | "WEAK";

export function scoreToRating(score: number): RatingLabel {
  if (score >= 80) return "STRONG";
  if (score >= 65) return "SOLID";
  if (score >= 50) return "NEUTRAL";
  if (score >= 35) return "CAUTION";
  return "WEAK";
}

export function ratingColor(rating: RatingLabel): string {
  const map: Record<RatingLabel, string> = {
    STRONG: "text-emerald-400",
    SOLID: "text-green-400",
    NEUTRAL: "text-yellow-400",
    CAUTION: "text-orange-400",
    WEAK: "text-red-400",
  };
  return map[rating];
}

export function ratingBg(rating: RatingLabel): string {
  const map: Record<RatingLabel, string> = {
    STRONG: "bg-emerald-950 border-emerald-700",
    SOLID: "bg-green-950 border-green-700",
    NEUTRAL: "bg-yellow-950 border-yellow-700",
    CAUTION: "bg-orange-950 border-orange-700",
    WEAK: "bg-red-950 border-red-700",
  };
  return map[rating];
}
