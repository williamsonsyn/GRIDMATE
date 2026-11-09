import type { AssetType } from '../types/api';

export const COLORS: Record<AssetType, string> = {
  solar: '#F59E0B', wind: '#06B6D4', hydro: '#3B82F6',
  battery: '#10B981', grid: '#EF4444', demand: '#8B5CF6',
};

export const TYPE_LABEL: Record<AssetType, string> = {
  solar: 'Solar', wind: 'Wind', hydro: 'Hydro', battery: 'Battery', grid: 'Grid', demand: 'Demand',
};

export const AXIS = { color: '#6B7A85', fontFamily: 'Instrument Sans Variable, system-ui, sans-serif' };
