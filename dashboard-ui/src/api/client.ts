import { responseContract, validateContract } from "./contracts";
let credentials = "";
export function setCredentials(user: string, password: string) {
  credentials =
    "Basic " +
    btoa(
      String.fromCharCode(...new TextEncoder().encode(user + ":" + password)),
    );
}
export function clearCredentials() {
  credentials = "";
}
export function authHeaders() {
  return { Authorization: credentials };
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch("/api/v1" + path, {
    ...options,
    headers: {
      ...authHeaders(),
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
  });
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401)
      window.dispatchEvent(new Event("sentinel-unauthorized"));
    throw new Error(data.error?.message || "Request failed. Please retry.");
  }
  const schema = responseContract(path, options.method);
  if (schema && !validateContract(data, schema))
    throw new Error(
      "The hub returned an unexpected response. Refresh or check its version.",
    );
  return data as T;
}
