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
  const controller = new AbortController();
  const cancel = () => controller.abort(options.signal?.reason);
  if (options.signal?.aborted) cancel();
  else options.signal?.addEventListener("abort", cancel, { once: true });
  let timedOut = false;
  const timeout = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, 15000);
  try {
    const response = await fetch("/api/v1" + path, {
      ...options,
      signal: controller.signal,
      headers: {
        ...authHeaders(),
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...options.headers,
      },
    });
    if (response.status === 401)
      window.dispatchEvent(new Event("sentinel-unauthorized"));
    let data;
    try {
      data = await response.json();
    } catch (error) {
      if (controller.signal.aborted) throw error;
      throw new Error(
        response.ok
          ? "The hub returned an unreadable response. Refresh or check its version."
          : `The hub returned HTTP ${response.status}. Please retry.`,
      );
    }
    if (!response.ok) {
      throw new Error(
        data?.error?.message ||
          `The hub returned HTTP ${response.status}. Please retry.`,
      );
    }
    const schema = responseContract(path, options.method);
    if (schema && !validateContract(data, schema))
      throw new Error(
        "The hub returned an unexpected response. Refresh or check its version.",
      );
    return data as T;
  } catch (error) {
    const writing = !["GET", "HEAD"].includes(
      (options.method || "GET").toUpperCase(),
    );
    if (timedOut && !options.signal?.aborted)
      throw new Error(
        writing
          ? "The hub took too long to respond. Your change may have completed; refresh before trying again."
          : "The hub took too long to respond. Check its connection and retry.",
      );
    if (error instanceof TypeError && !controller.signal.aborted)
      throw new Error(
        writing
          ? "Couldn’t reach your hub. Your change may have completed; refresh before trying again."
          : "Couldn’t reach your hub. Check its connection and retry.",
      );
    throw error;
  } finally {
    clearTimeout(timeout);
    options.signal?.removeEventListener("abort", cancel);
  }
}
