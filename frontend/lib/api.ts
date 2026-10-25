export async function api<T>(path: string, method = "GET", data?: unknown, token?: string): Promise<T> {
  const response = await fetch(`/api/${path}`, { method, headers: { "Content-Type": "application/json", ...(token ? { "X-Edit-Token": token } : {}) }, body: data === undefined ? undefined : JSON.stringify(data) });
  const result = response.status === 204 ? null : await response.json();
  if (!response.ok) {
    const error = result?.error;
    let message = error?.message || "The request failed.";
    const details = error?.details;
    if (error?.code === "PASS_LIMIT_EXCEEDED" && details?.travel_days_estimate != null)
      message += ` This route needs ${details.travel_days_estimate} rail travel days; your pass has ${details.remaining} remaining. Increase the pass allowance or choose a shorter route, then retry.`;
    if (error?.code === "TRIP_DURATION_EXCEEDED" && details?.required_days != null)
      message += ` Allow at least ${details.required_days} calendar days (currently ${details.available_days}), or reduce the stops/final stay, then retry.`;
    if (error?.code === "VALIDATION_ERROR" && details?.fields?.length)
      message += " " + details.fields.map((field: { location: string[]; message: string }) => `${field.location.filter(part => part !== "body").join(" · ")}: ${field.message}`).join("; ");
    throw new Error(message);
  }
  return result;
}
