export type ConnectionStep = { kind: string; label: string; estimated_minutes: number };
export type ConnectionPlan = { steps: ConnectionStep[]; before_departure_minutes: number; after_arrival_minutes: number; ferry_count: number; overnight_nights: number; arrival_time_status: string; notice: string; arrival_notes: string[] };
export type Transfer = { id?: string; connection_id?: string; origin_id?: string; destination_id?: string; source_url?: string; booking_url?: string; onward_url?: string; reservation_warning?: string; seasonal?: boolean; connection_plan?: ConnectionPlan; components?: { mode: string; origin?: string; destination?: string; description?: string; estimated_minutes: number }[] };
export const duration = (minutes: number) => `${Math.floor(minutes / 60)}h${minutes % 60 ? ` ${minutes % 60}m` : ""}`;

export type AirportAccess = { airport: string | null; name: string | null; route: string; estimated_minutes: number | null; ferry_crossings: number | null; status: string; notice: string };
