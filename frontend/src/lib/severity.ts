export type DriftStatus = 'unverified' | 'matched' | 'violated'

export const COLOR = {
  match: '#4ADE80',
  violate: '#FB4570',
  neutral: '#7C879C',
} as const

export function nodeColor(status: DriftStatus): { color: string; emissiveIntensity: number } {
  switch (status) {
    case 'matched':
      return { color: COLOR.match, emissiveIntensity: 1.0 }
    case 'violated':
      return { color: COLOR.violate, emissiveIntensity: 1.3 }
    default:
      return { color: COLOR.neutral, emissiveIntensity: 0.12 }
  }
}
