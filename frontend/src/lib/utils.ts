import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

export function newKey(prefix: string): string {
  const random = crypto.getRandomValues(new Uint8Array(12));
  return `${prefix}-${Array.from(random, (b) => b.toString(16).padStart(2, "0")).join("")}`;
}
